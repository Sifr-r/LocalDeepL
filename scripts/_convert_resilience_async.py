import re
path = "tests/core/ocr/test_ocr_resilience.py"
with open(path) as f:
    content = f.read()
content = re.sub(r"^import asyncio\n", "", content, flags=re.MULTILINE)
pattern = re.compile(
    r"^def (test_\w+)\((.*?)\):\n(.*?)^    async def _drive\(\) -> None:\n(.*?)^    asyncio\.run\(_drive\(\)\)\n",
    re.MULTILINE | re.DOTALL,
)
def convert(match):
    name = match.group(1)
    args = match.group(2)
    prelude = match.group(3)
    drive_body = match.group(4)
    dedented = re.sub(r"^    ", "", drive_body, flags=re.MULTILINE)
    return f"async def {name}({args}):\n{prelude}{dedented}"
new_content = pattern.sub(convert, content)
new_content = re.sub(r"    asyncio\.run\(_drive\(\)\)\n", "", new_content)
with open(path, "w") as f:
    f.write(new_content)
print("done")
