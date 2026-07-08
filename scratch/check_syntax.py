import re

files_to_check = [
    r'e:\obsidian\vault\Torchain-main\windows\setup.bat',
    r'e:\obsidian\vault\Torchain-main\windows\internet.bat',
    r'e:\obsidian\vault\Torchain-main\windows\uninstall.bat'
]

color_vars = ['%GREEN%', '%RESET%', '%RED%', '%YELLOW%', '%CYAN%', '%MAGENTA%']

for file_path in files_to_check:
    print(f"\nChecking: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Let's find all occurrences of color variables and see if they are inside parenthesis blocks
    # We can do this by scanning line-by-line and keeping track of nesting or simple heuristics.
    lines = content.splitlines()
    in_block = 0
    for idx, line in enumerate(lines):
        line_num = idx + 1
        stripped = line.strip()
        
        # Track opening/closing parenthesis in block
        # (This is simplified but good enough for batch files)
        if stripped.endswith('('):
            in_block += 1
        
        # Check if line contains any color variables when we are inside a block
        # (or even generally if it's on a line inside parentheses)
        for var in color_vars:
            if var in line:
                # We want to identify if this is inside an 'if' or general parenthesis block
                # Let's print it if it contains %VAR% inside any parenthesis context
                print(f"Line {line_num}: {line.strip()}")
                
        if stripped == ')':
            in_block -= 1
