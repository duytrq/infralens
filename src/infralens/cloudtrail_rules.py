"""Exact rule-ID correlation through explicit EC2 request schemas only."""

import re

RULE_TYPES = {
    "aws_vpc_security_group_ingress_rule": "Ingress",
    "aws_vpc_security_group_egress_rule": "Egress",
}
RULE_FIELDS = {
    "ip_protocol": "IpProtocol",
    "from_port": "FromPort",
    "to_port": "ToPort",
    "cidr_ipv4": "CidrIpv4",
    "cidr_ipv6": "CidrIpv6",
    "prefix_list_id": "PrefixListId",
    "referenced_security_group_id": "ReferencedGroupId",
    "description": "Description",
}


def rule_operations(resource):
    direction = RULE_TYPES[resource.resource_type]
    if resource.actions == ("delete",):
        return {f"RevokeSecurityGroup{direction}": ["(resource deletion)"]}
    operations = {}
    for change in resource.attributes:
        if len(change.path) != 1 or change.path[0] not in RULE_FIELDS:
            continue
        field = change.path[0]
        operations.setdefault("ModifySecurityGroupRules", []).append(field)
        if field == "description":
            operations[f"UpdateSecurityGroupRuleDescriptions{direction}"] = [field]
    return operations


def _one(body, keys):
    found = [body[key] for key in keys if key in body]
    return found[0] if len(found) == 1 else None


def match_rule_request(raw, group_id, rule_id, attributes):
    """Return matched fields, False for another rule, None for unresolved schema.

    Accept the EC2 Query request envelope or its explicit camel-case set form.
    Never search descriptions, tags, response payloads or arbitrary nested keys
    for a coincidental ID. Unknown shapes reduce coverage instead of matching.
    """
    name = raw["eventName"]
    request = raw.get("requestParameters")
    if not isinstance(request, dict):
        return None
    wrapper = name + "Request"
    if wrapper in request:
        if "GroupId" in request or "groupId" in request:
            return None
        request = request[wrapper]
    if not isinstance(request, dict):
        return None
    group = _one(request, ("GroupId", "groupId"))
    if not isinstance(group, str):
        return None
    if group != group_id:
        return False
    pascal = "GroupId" in request
    id_key = "SecurityGroupRuleId" if pascal else "securityGroupRuleId"
    if name.startswith("RevokeSecurityGroup"):
        rows = (
            _one(request, ("SecurityGroupRuleId", "SecurityGroupRuleIds"))
            if pascal
            else request.get("securityGroupRuleIdSet")
        )
    elif name == "ModifySecurityGroupRules":
        rows = (
            _one(request, ("SecurityGroupRule", "SecurityGroupRules"))
            if pascal
            else request.get("securityGroupRuleSet")
        )
    else:
        rows = (
            _one(
                request,
                ("SecurityGroupRuleDescription", "SecurityGroupRuleDescriptions"),
            )
            if pascal
            else request.get("securityGroupRuleDescriptionSet")
        )
    if not pascal:
        if not isinstance(rows, dict):
            return None
        rows = rows.get("items")
    if isinstance(rows, (str, dict)):
        rows = [rows]
    if not isinstance(rows, list) or not rows:
        return None
    unresolved = False
    matched = set()
    for row in rows:
        identity = (
            row
            if isinstance(row, str) and name.startswith("Revoke")
            else row.get(id_key)
            if isinstance(row, dict)
            else None
        )
        if not isinstance(identity, str) or not re.fullmatch(
            r"sgr-[0-9a-f]{17}", identity
        ):
            unresolved = True
            continue
        if identity != rule_id:
            continue
        if name != "ModifySecurityGroupRules":
            matched.update(attributes)
            continue
        update = row.get("SecurityGroupRule" if pascal else "securityGroupRule")
        if not isinstance(update, dict):
            unresolved = True
            continue
        keys = {
            field: spelling if pascal else spelling[0].lower() + spelling[1:]
            for field, spelling in RULE_FIELDS.items()
        }
        matched.update(field for field in attributes if keys[field] in update)
        if not any(key in update for key in keys.values()):
            unresolved = True
    return sorted(matched) if matched else None if unresolved else False
