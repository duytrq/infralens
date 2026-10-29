"""Terminal-only excerpts of changed declarations, never serialized or uploaded."""

import json
from itertools import islice
from pathlib import Path

from infralens.drift_reporting import changed_values, priority
from infralens.reporting import _severity
from infralens.source_locations import (
    SourceIssue,
    SourceLocator,
    _json_labeled,
    _literal,
    _properties,
    _unique_pairs,
    _whitespace,
    parse_address,
)

MAX_LINES = 12


def _trees(node):
    from lark import Tree

    return [child for child in node.children if isinstance(child, Tree)]


def _unwrap(node):
    while node.data in ("expr_term", "object_elem_key") and len(_trees(node)) == 1:
        node = _trees(node)[0]
    return node


def _expression_member(text, node, path):
    node = _unwrap(node)
    if not path:
        return node
    if node.data == "tuple" and isinstance(path[0], int):
        items = [item for item in _trees(node) if item.data != "new_line_or_comment"]
        index = path[0]
        if 0 <= index < len(items):
            return _expression_member(text, items[index], path[1:])
        return None
    if node.data != "object":
        return None
    for member in _trees(node):
        if member.data != "object_elem":
            continue
        parts = _trees(member)
        if _literal(text, _unwrap(parts[0])) == path[0]:
            return (
                member
                if len(path) == 1
                else _expression_member(text, parts[-1], path[1:])
            )
    return None


def _hcl_field(text, body, path):
    if not path:
        return None
    blocks = []
    for child in _trees(body):
        parts = _trees(child)
        if not parts or _literal(text, parts[0]) != path[0]:
            continue
        if child.data == "attribute":
            if len(path) == 1:
                return child
            return _expression_member(text, parts[-1], path[1:])
        if child.data == "block":
            blocks.append(child)
    if blocks:
        index = path[1] if len(path) > 1 and isinstance(path[1], int) else 0
        rest = path[2:] if len(path) > 1 and isinstance(path[1], int) else path[1:]
        if 0 <= index < len(blocks):
            return _hcl_field(text, _trees(blocks[index])[-1], rest)
    return None


def _hcl_spans(text, labels, paths, tree=None):
    import hcl2

    tree = tree if tree is not None else hcl2.parses_to_tree(text)
    body = _trees(tree)[0]
    matches = []
    for node in _trees(body):
        if node.data != "block":
            continue
        parts = _trees(node)
        if (
            _literal(text, parts[0]) == "resource"
            and tuple(_literal(text, p) for p in parts[1:-1]) == labels
        ):
            matches.append(node)
    if len(matches) != 1:
        return []
    result = []
    for path, hidden in paths:
        node = _hcl_field(text, _trees(matches[0])[-1], path)
        if node is not None:
            result.append((node.meta.start_pos, node.meta.end_pos, hidden, path))
    return result


def _json_field(text, body, path):
    if not path or not isinstance(path[0], str) or text[body] != "{":
        return None
    for key, start, end, key_start in _properties(text, body):
        if key != path[0]:
            continue
        if len(path) == 1:
            return key_start, end
        if isinstance(path[1], int):
            return None
        return _json_field(text, start, path[1:])
    return None


def _json_spans(text, labels, paths, tree=None):
    json.loads(text, object_pairs_hook=_unique_pairs)
    matches = []
    for kind, start, _, _ in _properties(text, _whitespace(text, 0)):
        if kind == "resource":
            matches.extend(
                body
                for names, body, _, _ in _json_labeled(text, start, 2)
                if names == labels
            )
    if len(matches) != 1:
        return []
    result = []
    for path, hidden in paths:
        span = _json_field(text, matches[0], path)
        if span:
            result.append((*span, hidden, path))
    return result


def _changed_paths(resource):
    for attribute in resource.attributes:
        for path, before, after in islice(
            changed_values(attribute.path, attribute.before, attribute.after), 40
        ):
            if not path:
                continue
            # tags_all is provider-derived; its configured expression is tags.
            path = ("tags", *path[1:]) if path[0] == "tags_all" else path
            statuses = {before["status"], after["status"]}
            hidden = (
                "sensitive"
                if "sensitive" in statuses
                else "unknown"
                if "unknown" in statuses
                else None
            )
            yield path, hidden


def source_excerpts(result, root, *, data_dir=None, color=False, severity=None):
    from lark.exceptions import LarkError

    locator = SourceLocator(Path(root), data_dir)
    cache = {}
    output = {}
    for resource in result.resources:
        if severity is not None and priority(resource) not in severity:
            continue
        lines = []
        try:
            source = locator.locate(resource)
            locations = source.get("locations", [])
            if source["status"] != "located" or len(locations) != 1:
                raise SourceIssue(source.get("reason", "source_unavailable"))
            location = locations[0]
            file = Path(location["file"]).resolve()
            try:
                file.relative_to(locator.root)
            except ValueError:
                raise SourceIssue("outside_project_root") from None
            if file not in cache:
                text = locator._read(file)
                if location["syntax"] == "hcl":
                    import hcl2

                    tree = hcl2.parses_to_tree(text)
                else:
                    tree = None
                cache[file] = text, tree
            text, tree = cache[file]
            _, labels = parse_address(resource.address)
            paths = list(islice(_changed_paths(resource), 40))
            spans = (_json_spans if location["syntax"] == "json" else _hcl_spans)(
                text, labels, paths, tree
            )
            if not spans:
                raise SourceIssue("changed_fields_not_declared")
            lines.append("  Current configuration (changed fields):")
            spans = [
                (
                    start,
                    end,
                    next(
                        (
                            mask
                            for lo, hi, mask, _ in spans
                            if mask and start <= hi and lo <= end
                        ),
                        hidden,
                    ),
                    path,
                )
                for start, end, hidden, path in spans
            ]
            seen = set()
            for start, end, hidden, path in sorted(spans, key=lambda s: (s[0], s[1])):
                if (start, end) in seen:
                    continue
                seen.add((start, end))
                first = text.count("\n", 0, start) + 1
                code = text[start:end].splitlines()
                if hidden:
                    code = [f"{path[-1]} = [{hidden}]"]
                for offset, content in enumerate(code):
                    if len(lines) >= MAX_LINES:
                        break
                    content = "".join(
                        c for c in content.expandtabs(4) if c.isprintable()
                    )
                    if len(content) > 180:
                        content = content[:180] + "..."
                    line = f"  > {first + offset} | {content}"
                    lines.append(_severity(line, priority(resource), color))
                if len(lines) >= MAX_LINES:
                    lines.append("    ... source excerpt truncated")
                    break
        except (
            SourceIssue,
            OSError,
            RuntimeError,
            LarkError,
            ValueError,
            TypeError,
            IndexError,
            RecursionError,
        ):
            lines = [
                "  Source excerpt unavailable for changed fields; "
                "see location and value diff."
            ]
        output[resource.address] = lines
    return output
