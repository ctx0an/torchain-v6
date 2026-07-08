import os
import urllib.request
import zipfile
import tempfile
import shutil

def download_and_extract():
    url = "https://github.com/guardianproject/orbot-android/releases/download/17.9.5-RC-1-tor-0.4.9.9/Orbot-17.9.5-RC-1-tor-0.4.9.9-fullperm-universal-release.apk"
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    jni_dir = os.path.join(project_root, "app", "src", "main", "jniLibs")
    assets_dir = os.path.join(project_root, "app", "src", "main", "assets")
    
    # Create target directories
    os.makedirs(assets_dir, exist_ok=True)
    abis = ["arm64-v8a", "armeabi-v7a", "x86", "x86_64"]
    for abi in abis:
        os.makedirs(os.path.join(jni_dir, abi), exist_ok=True)
        
    print(f"Downloading Orbot APK from:\n{url}")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        apk_path = os.path.join(tmpdir, "orbot.apk")
        
        # Download file
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(apk_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
            
        print("Download complete. Extracting files...")
        
        with zipfile.ZipFile(apk_path, 'r') as zip_ref:
            # Extract libraries
            for file_info in zip_ref.infolist():
                filename = file_info.filename
                
                # Check for native libs
                for abi in abis:
                    if filename == f"lib/{abi}/libtor.so":
                        target_path = os.path.join(jni_dir, abi, "libtor.so")
                        with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        print(f"  -> Extracted {abi}/libtor.so")
                    elif filename == f"lib/{abi}/libhev-socks5-tunnel.so":
                        target_path = os.path.join(jni_dir, abi, "libhev-socks5-tunnel.so")
                        with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                            shutil.copyfileobj(source, target)
                        print(f"  -> Extracted {abi}/libhev-socks5-tunnel.so")
                
                # Check for geoip databases
                if filename == "assets/geoip":
                    target_path = os.path.join(assets_dir, "geoip")
                    with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    print("  -> Extracted assets/geoip")
                elif filename == "assets/geoip6":
                    target_path = os.path.join(assets_dir, "geoip6")
                    with zip_ref.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)
                    print("  -> Extracted assets/geoip6")

    print("\nExtraction finished successfully!")

if __name__ == "__main__":
    download_and_extract()
