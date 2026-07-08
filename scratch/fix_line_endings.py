import os

windows_dir = r"e:\obsidian\vault\Torchain-main\windows"
files = [f for f in os.listdir(windows_dir) if f.endswith((".bat", ".cmd"))]

for filename in files:
    filepath = os.path.join(windows_dir, filename)
    with open(filepath, "rb") as f:
        content = f.read()
    
    # Detect line endings
    has_lf = b"\n" in content
    has_crlf = b"\r\n" in content
    
    if has_lf and not has_crlf:
        print(f"{filename}: Has LF line endings")
    elif has_crlf and has_lf:
        # Mixed line endings
        # Let's count how many of each
        lf_count = content.count(b"\n")
        crlf_count = content.count(b"\r\n")
        if lf_count != crlf_count:
            print(f"{filename}: Mixed line endings (LF={lf_count}, CRLF={crlf_count})")
        else:
            print(f"{filename}: Clear CRLF")
    else:
        print(f"{filename}: Other/Unknown")
        
    # Convert to CRLF
    # Replace all \r\n with \n first, then replace all \n with \r\n
    normalized = content.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if normalized != content:
        print(f"--> Converting {filename} to CRLF")
        with open(filepath, "wb") as f:
            f.write(normalized)
    else:
        print(f"{filename}: Already strict CRLF")
