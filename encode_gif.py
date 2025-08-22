# encode_gif.py
import base64
import os

def encode_gif_to_base64(folder_path="gif_assets"):
    for filename in os.listdir(folder_path):
        if filename.endswith(".gif"):
            file_path = os.path.join(folder_path, filename)
            with open(file_path, "rb") as f:
                encoded = base64.b64encode(f.read()).decode()
                out_path = os.path.join(folder_path, filename + ".txt")
                with open(out_path, "w") as out_file:
                    out_file.write(encoded)
                print(f"{filename} → Base64に変換しました")

# 実行用（オプション）
if __name__ == "__main__":
    encode_gif_to_base64()