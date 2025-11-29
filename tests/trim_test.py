import pyvips
import os


os.add_dll_directory("C:\\Projects\\libraries\\vips-dev-8.17\\bin")
def trim_image_vips(image_path, output_path):
    """
    pyvips를 사용하여 이미지의 배경을 자동으로 잘라냅니다.
    """
    try:
        image = pyvips.Image.new_from_file(image_path)

        # 배경색을 (0,0) 픽셀로 간주하고, 내용이 있는 영역의 경계 상자를 찾음
        # left, top, width, height를 반환
        left, top, width, height = image.find_trim()

        # 해당 영역을 잘라냄
        trimmed_image = image.crop(left, top, width, height)

        trimmed_image.write_to_file(output_path)
        print(f"pyvips로 이미지 트림 성공: {output_path}")

    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    trim_image_vips("1.jpg", "1_trimmed.jpg")