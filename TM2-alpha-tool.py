import sys
import os

def process_tm2_alpha(file_path):
    """处理单个TM2文件并覆盖源文件"""
    # 读取文件内容到bytearray以便修改
    with open(file_path, 'rb') as f:
        data = bytearray(f.read())
    
    # 验证文件头
    if len(data) < 64 or data[0:4] != b'TIM2':
        raise ValueError("Invalid TM2 file format")
    
    # 读取色位数（小端序）
    n = int.from_bytes(data[30:32], byteorder='little')
    if n <= 0:
        raise ValueError("Invalid color depth value")
    
    # 计算调色板位置和大小
    file_size = len(data)
    palette_size = 4 * n
    palette_start = file_size - palette_size
    
    # 验证调色板位置有效性
    if palette_start < 64 or palette_start + palette_size > file_size:
        raise ValueError("Invalid palette position")
    
    # 处理每个调色板项的alpha通道
    for i in range(n):
        alpha_pos = palette_start + i * 4 + 3
        original = data[alpha_pos]
        data[alpha_pos] = (original + 1) // 2  # 向上取整处理
    
    # 覆盖写入源文件
    with open(file_path, 'wb') as f:
        f.write(data)

def batch_process(paths):
    """批量处理文件/目录"""
    processed = 0
    errors = []
    
    for path in paths:
        # 处理单个文件
        if os.path.isfile(path):
            if path.lower().endswith('.tm2'):
                try:
                    process_tm2_alpha(path)
                    processed += 1
                except Exception as e:
                    errors.append(f"{path}: {str(e)}")
        # 处理目录
        elif os.path.isdir(path):
            for root, _, files in os.walk(path):
                for file in files:
                    if file.lower().endswith('.tm2'):
                        full_path = os.path.join(root, file)
                        try:
                            process_tm2_alpha(full_path)
                            processed += 1
                        except Exception as e:
                            errors.append(f"{full_path}: {str(e)}")
        else:
            errors.append(f"{path}: Path does not exist")
    
    return processed, errors

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python tm2_alpha_adjust.py <file/dir1> [file/dir2 ...]")
        print("Example:")
        print("  Single file : python tm2_alpha_adjust.py image.tm2")
        print("  Multiple    : python tm2_alpha_adjust.py *.tm2")
        print("  Directory   : python tm2_alpha_adjust.py ./textures/")
        sys.exit(1)
    
    try:
        total, errors = batch_process(sys.argv[1:])
        print(f"Successfully processed {total} files")
        
        if errors:
            print("\nErrors occurred:")
            for error in errors:
                print(f"  {error}")
            sys.exit(2)
    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(130)