"""Locate resource blocks in current configuration without evaluating expressions."""

import json
import re
from dataclasses import dataclass, replace
from pathlib import Path

from infralens.drift import DriftResult

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TOTAL_BYTES = 16 * 1024 * 1024
MAX_FILES_PER_MODULE = 200
MAX_MODULES = 100
MAX_MODULE_DEPTH = 64
_NAME = re.compile(r"[^\W\d][\w-]*", re.UNICODE)
_DECODER = json.JSONDecoder()
_NOTE = (
    "Source locations refer to resource blocks in current local configuration, "
    "not historical plan contents or exact changed-attribute expressions. "
    "Unavailable or ambiguous locations do not change the drift verdict."
)


class SourceIssue(Exception):
    """A controlled reason with no source contents or parser diagnostics."""


@dataclass(frozen=True)
class Block:
    kind: str
    labels: tuple[str, ...]
    file: str
    start_line: int
    end_line: int
    syntax: str
    module_source: str | None = None

    def location(self):
        return {
            "file": self.file,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "syntax": self.syntax,
        }


def parse_address(address: str):
    """Discard instance selectors structurally, including quoted dots/brackets."""
    position = 0

    def name():
        nonlocal position
        match = _NAME.match(address, position)
        if not match:
            raise SourceIssue("unsupported_address")
        position = match.end()
        return match[0]

    def separator():
        nonlocal position
        if address[position : position + 1] != ".":
            raise SourceIssue("unsupported_address")
        position += 1

    def selector():
        nonlocal position
        if address[position : position + 1] != "[":
            return
        try:
            key, end = _DECODER.raw_decode(address, position + 1)
        except ValueError:
            raise SourceIssue("unsupported_address") from None
        if not (isinstance(key, str) or type(key) is int and key >= 0):
            raise SourceIssue("unsupported_address")
        if address[end : end + 1] != "]":
            raise SourceIssue("unsupported_address")
        position = end + 1

    modules = []
    while address.startswith("module.", position):
        position += len("module.")
        modules.append(name())
        selector()
        separator()
        if len(modules) > MAX_MODULE_DEPTH:
            raise SourceIssue("module_depth_limit")
    resource_type = name()
    separator()
    resource_name = name()
    selector()
    if position != len(address):
        raise SourceIssue("unsupported_address")
    return tuple(modules), (resource_type, resource_name)


def _literal(text, node):
    if node.data == "identifier":
        return str(node.children[0])
    if node.data != "string":
        return None
    try:
        value = json.loads(text[node.meta.start_pos : node.meta.end_pos])
    except ValueError:
        return None
    if isinstance(value, str) and "${" not in value and "%{" not in value:
        return value
    return None


def _hcl_blocks(text, path):
    import hcl2
    from lark import Tree
    from lark.exceptions import LarkError

    try:
        tree = hcl2.parses_to_tree(text)
    except (LarkError, ValueError, RecursionError):
        raise SourceIssue("parse_error") from None
    body = next(child for child in tree.children if isinstance(child, Tree))
    blocks = []
    for node in body.children:
        if not isinstance(node, Tree) or node.data != "block":
            continue
        parts = [child for child in node.children if isinstance(child, Tree)]
        kind = _literal(text, parts[0])
        if kind not in ("resource", "module"):
            continue
        labels = tuple(_literal(text, part) for part in parts[1:-1])
        if len(labels) != (2 if kind == "resource" else 1) or None in labels:
            continue
        module_source = None
        if kind == "module":
            sources = []
            for attribute in parts[-1].children:
                if not isinstance(attribute, Tree) or attribute.data != "attribute":
                    continue
                children = [c for c in attribute.children if isinstance(c, Tree)]
                if _literal(text, children[0]) != "source":
                    continue
                expression = children[-1]
                if expression.data == "expr_term" and len(expression.children) == 1:
                    value = expression.children[0]
                    if isinstance(value, Tree):
                        sources.append(_literal(text, value))
            if len(sources) == 1:
                module_source = sources[0]
        blocks.append(
            Block(
                kind,
                labels,
                str(path),
                node.meta.line,
                node.meta.end_line,
                "hcl",
                module_source,
            )
        )
    return blocks


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError


def _whitespace(text, position):
    while position < len(text) and text[position] in " \t\r\n":
        position += 1
    return position


def _properties(text, position):
    """Read object member spans after standard JSON validation."""
    position = _whitespace(text, position + 1)
    while text[position] != "}":
        key_start = position
        key, position = _DECODER.raw_decode(text, position)
        position = _whitespace(text, position)
        position = _whitespace(text, position + 1)  # colon
        start = position
        _, end = _DECODER.raw_decode(text, start)
        yield key, start, end, key_start
        position = _whitespace(text, end)
        if text[position] == "}":
            return
        position = _whitespace(text, position + 1)  # comma


def _objects(text, position, depth=0):
    if depth > MAX_MODULE_DEPTH:
        raise SourceIssue("parse_error")
    if text[position] == "{":
        yield position
    elif text[position] == "[":
        position = _whitespace(text, position + 1)
        while text[position] != "]":
            yield from _objects(text, position, depth + 1)
            _, end = _DECODER.raw_decode(text, position)
            position = _whitespace(text, end)
            if text[position] == "]":
                return
            position = _whitespace(text, position + 1)


def _json_labeled(text, position, remaining, labels=(), label_start=None):
    for body in _objects(text, position):
        if remaining == 0:
            _, end = _DECODER.raw_decode(text, body)
            yield labels, body, end, label_start
            continue
        for key, start, _, key_start in _properties(text, body):
            yield from _json_labeled(
                text, start, remaining - 1, (*labels, key), key_start
            )


def _json_blocks(text, path):
    try:
        parsed = json.loads(
            text, object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
        )
        if not isinstance(parsed, dict):
            raise ValueError
        blocks = []
        for kind, position, _, _ in _properties(text, _whitespace(text, 0)):
            if kind not in ("resource", "module"):
                continue
            for labels, body, end, start in _json_labeled(
                text, position, 2 if kind == "resource" else 1
            ):
                source = None
                if kind == "module":
                    for key, value_start, _, _ in _properties(text, body):
                        if key == "source":
                            value, _ = _DECODER.raw_decode(text, value_start)
                            if isinstance(value, str):
                                source = value
                blocks.append(
                    Block(
                        kind,
                        labels,
                        str(path),
                        text.count("\n", 0, start) + 1,
                        text.count("\n", 0, end - 1) + 1,
                        "json",
                        source,
                    )
                )
        return blocks
    except (ValueError, TypeError, IndexError, RecursionError):
        raise SourceIssue("parse_error") from None


class SourceLocator:
    def __init__(self, root: Path, data_dir: str | None = None):
        self.root = root.resolve()
        data = Path(data_dir) if data_dir else Path(".terraform")
        self.data = data if data.is_absolute() else self.root / data
        self.cache = {}
        self.total_bytes = 0
        self.manifest = None

    def _read(self, path):
        try:
            size = path.stat().st_size
            available = min(MAX_FILE_BYTES, MAX_TOTAL_BYTES - self.total_bytes)
            if size > available:
                raise SourceIssue("source_size_limit")
            with path.open("rb") as stream:
                content = stream.read(available + 1)
            if len(content) > available:
                raise SourceIssue("source_size_limit")
            self.total_bytes += len(content)
            return content.decode("utf-8-sig")
        except (OSError, UnicodeError):
            raise SourceIssue("source_unreadable") from None

    def _module(self, directory):
        directory = directory.resolve()
        if directory in self.cache:
            return self.cache[directory]
        if len(self.cache) >= MAX_MODULES:
            raise SourceIssue("module_limit")
        try:
            files = sorted(
                file
                for file in directory.iterdir()
                if not file.name.startswith(".")
                and file.name.endswith((".tf", ".tf.json"))
                and file.is_file()
            )
        except OSError:
            raise SourceIssue("module_unavailable") from None
        if len(files) > MAX_FILES_PER_MODULE:
            raise SourceIssue("source_file_limit")
        blocks, problems = [], []
        for file in files:
            try:
                path = file.resolve()
                text = self._read(path)
                blocks.extend(
                    (_json_blocks if file.name.endswith(".json") else _hcl_blocks)(
                        text, path
                    )
                )
            except SourceIssue as issue:
                problems.append(str(issue))
        self.cache[directory] = (blocks, problems)
        return blocks, problems

    def _installed(self, key):
        if self.manifest is None:
            path = self.data / "modules" / "modules.json"
            if not path.is_file():
                raise SourceIssue("module_not_installed")
            try:
                value = json.loads(self._read(path), object_pairs_hook=_unique_pairs)
                modules = value["Modules"]
                if not isinstance(modules, list):
                    raise ValueError
                manifest = {}
                for module in modules:
                    name, directory = module["Key"], module["Dir"]
                    if not isinstance(name, str) or not isinstance(directory, str):
                        raise ValueError
                    if name in manifest:
                        raise ValueError
                    manifest[name] = directory
                self.manifest = manifest
            except (ValueError, TypeError, KeyError):
                raise SourceIssue("module_manifest_invalid") from None
        directory = self.manifest.get(key)
        if not directory:
            raise SourceIssue("module_not_installed")
        path = Path(directory)
        return path if path.is_absolute() else self.root / path

    def locate(self, resource):
        info = {"status": "unavailable", "context": "current_configuration"}
        try:
            modules, labels = parse_address(resource.address)
            if labels[0] != resource.resource_type:
                raise SourceIssue("unsupported_address")
            info["block_address"] = "".join(
                f"module.{name}." for name in modules
            ) + ".".join(labels)
            directory = self.root
            for index, name in enumerate(modules):
                blocks, problems = self._module(directory)
                if problems:
                    raise SourceIssue(problems[0])
                calls = [
                    block
                    for block in blocks
                    if block.kind == "module" and block.labels == (name,)
                ]
                if len(calls) != 1:
                    raise SourceIssue(
                        "module_not_declared" if not calls else "ambiguous_module"
                    )
                source = calls[0].module_source
                if source and source.startswith(("./", "../")):
                    directory = directory / source
                else:
                    directory = self._installed(".".join(modules[: index + 1]))
            blocks, problems = self._module(directory)
            matches = [
                block
                for block in blocks
                if block.kind == "resource" and block.labels == labels
            ]
            if matches:
                info["locations"] = [block.location() for block in matches]
            if problems:
                raise SourceIssue(problems[0])
            if not matches:
                raise SourceIssue("resource_not_declared")
            if len(matches) > 1:
                info.update(status="ambiguous", reason="multiple_declarations")
            else:
                info["status"] = "located"
        except (OSError, RuntimeError):
            info["reason"] = "source_unreadable"
        except SourceIssue as issue:
            info["reason"] = str(issue)
        return info


def enrich_source_locations(result: DriftResult, root: Path, data_dir=None):
    if not result.resources:
        return result
    locator = SourceLocator(root, data_dir)
    return replace(
        result,
        resources=tuple(
            replace(resource, source=locator.locate(resource))
            for resource in result.resources
        ),
        notes=result.notes + (_NOTE,),
    )
