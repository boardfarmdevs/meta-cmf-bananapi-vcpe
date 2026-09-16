"""Extract policy value types without unrelated native platform headers."""

import re


def policy_types(header):
    declarations = {}
    for match in re.finditer(r'typedef\s+(?:struct|enum|union)\s*\{.*?^\}[^;\n]*;', header, re.S | re.M):
        declaration = match.group()
        name = re.search(r'(\w+)\s*;$', declaration).group(1)
        declarations[name] = declaration
    for match in re.finditer(r'^typedef[^\n{;]+;', header, re.M):
        declaration = match.group()
        name = re.search(r'(\w+)\s*(?:\[[^]]+\])?\s*;$', declaration)
        if name:
            declarations[name.group(1)] = declaration
    macros = dict(re.findall(r'^#define\s+(\w+)\s+([^\n]+)', header, re.M))
    owners = {}
    for name, declaration in declarations.items():
        if declaration.startswith('typedef enum'):
            for token in re.findall(r'^\s*(\w+)\s*(?:=|,)', declaration, re.M):
                owners.setdefault(token, name)
    seen = set()
    output = []

    def include(name):
        if name in seen:
            return
        seen.add(name)
        value = declarations.get(name)
        if value is None:
            if name in macros:
                value = '#define ' + name + ' ' + macros[name]
            elif name in owners:
                include(owners[name])
                return
            else:
                return
        for token in re.findall(r'\b\w+\b', value):
            if token != name:
                include(token)
        output.append(value)

    include('em_policy_cfg_params_t')
    return '\n'.join(output)


def method(source, signature):
    return re.search(re.escape(signature) + r'\(.*?\n\}', source, re.S).group()


def received_policy_type(header):
    return re.search(r'struct em_received_policy_t \{.*?\n\};', header, re.S).group()
