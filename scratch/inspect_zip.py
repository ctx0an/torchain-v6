import urllib.request
import zipfile
import io

url = "https://github.com/bjia56/portable-python/releases/download/cpython-v3.9.25-build.0/python-full-3.9.25-windows-x86_64.zip"
print("Downloading...")
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
with urllib.request.urlopen(req) as response:
    zip_data = response.read()

print("Zip downloaded. Size:", len(zip_data))
with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    names = z.namelist()
    print("Total files:", len(names))
    print("First 15 files:")
    for name in names[:15]:
        print(" -", name)
