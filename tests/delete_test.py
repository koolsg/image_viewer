import os
import send2trash

# delete_test 폴더의 절대 경로
folder_path = os.path.abspath('delete_test')

# 안전하게 디렉터리가 존재하는지 확인하고, 없으면 조용히 건너뜀
if not os.path.isdir(folder_path):
    print(f"delete_test folder not found at {folder_path}; skipping cleanup.")
else:
    # 폴더 안의 모든 파일 목록을 읽어서 저장
    files = os.listdir(folder_path)

    # 각 파일을 절대 경로로 변환하고, 파일인지 확인 후 휴지통으로 보냄
    for file in files:
        print(f"처리 중: {file}")
        file_path = os.path.join(folder_path, file)
        if os.path.isfile(file_path):
            send2trash.send2trash(file_path)
            print(f"{file_path} 삭제 성공")

"""
for file in files:
    file_path = os.path.join('delete_test', file)
    if os.path.isfile(file_path):
        send2trash.send2trash(file_path)
        print(f"{file_path} 삭제 성공")
        """
