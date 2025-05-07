import os
import datetime
import pydicom
import pandas as pd
import glob
from collections import defaultdict

def scan_dicom_directory(directory_path, patient_id=None):
    """Quét thư mục để tìm và phân loại các file DICOM theo loại"""
    print(f"Đang quét thư mục {directory_path}...")
    
    # Khởi tạo các danh sách file
    ct_planning_files = []
    cbct_files = []
    rt_record_files = []
    rt_structure_files = []
    rt_dose_files = []
    rt_plan_files = []
    
    # Pattern tìm kiếm
    if patient_id:
        print(f"Tìm kiếm ảnh cho bệnh nhân {patient_id}")
        search_pattern = f"**/*{patient_id}*.dcm"
    else:
        search_pattern = "**/*.dcm"
    
    # Tìm tất cả file DICOM
    all_dcm_files = glob.glob(os.path.join(directory_path, search_pattern), recursive=True)
    print(f"Tìm thấy tổng cộng {len(all_dcm_files)} file DICOM")
    
    # Phân loại theo quy ước đặt tên
    for file_path in all_dcm_files:
        filename = os.path.basename(file_path)
        
        # Phân loại dựa vào tiền tố
        if filename.startswith("CT."):
            ct_planning_files.append(file_path)
        elif filename.startswith("RI."):
            cbct_files.append(file_path)
        elif filename.startswith("RT."):
            rt_record_files.append(file_path)
        elif filename.startswith("RS."):
            rt_structure_files.append(file_path)
        elif filename.startswith("RD."):
            rt_dose_files.append(file_path)
        elif filename.startswith("RP."):
            rt_plan_files.append(file_path)
        else:
            # Nếu không dựa được vào tên, thử đọc metadata
            try:
                dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                modality = getattr(dcm, 'Modality', 'Unknown')
                
                if modality == 'CT':
                    ct_planning_files.append(file_path)
                elif modality in ['RTIMAGE', 'RI']:
                    cbct_files.append(file_path)
                elif modality == 'RTRECORD':
                    rt_record_files.append(file_path)
                elif modality == 'RTSTRUCT':
                    rt_structure_files.append(file_path)
                elif modality == 'RTDOSE':
                    rt_dose_files.append(file_path)
                elif modality == 'RTPLAN':
                    rt_plan_files.append(file_path)
            except Exception as e:
                print(f"Không thể đọc file {filename}: {e}")
    
    # In thống kê
    print("\nKết quả phân loại:")
    print(f"CT lập kế hoạch: {len(ct_planning_files)} file")
    print(f"CBCT kiểm tra: {len(cbct_files)} file")
    print(f"RT Record: {len(rt_record_files)} file")
    print(f"RT Structure: {len(rt_structure_files)} file")
    print(f"RT Dose: {len(rt_dose_files)} file")
    print(f"RT Plan: {len(rt_plan_files)} file")
    
    return {
        'ct_planning': ct_planning_files,
        'cbct': cbct_files,
        'rt_record': rt_record_files,
        'rt_structure': rt_structure_files,
        'rt_dose': rt_dose_files,
        'rt_plan': rt_plan_files
    }

def save_classification_results(results, output_dir, patient_id=None):
    """Lưu kết quả phân loại vào các file txt"""
    # Tạo thư mục đầu ra
    os.makedirs(output_dir, exist_ok=True)
    
    prefix = f"{patient_id}_" if patient_id else ""
    
    # Lưu từng danh sách vào file
    for category, file_list in results.items():
        if file_list:
            file_path = os.path.join(output_dir, f"{prefix}{category}_files.txt")
            with open(file_path, 'w') as f:
                for item in file_list:
                    f.write(f"{item}\n")
            print(f"Đã lưu {len(file_list)} đường dẫn vào {file_path}")

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Phân loại ảnh CT và CBCT từ thư mục DICOM')
    parser.add_argument('directory', help='Đường dẫn đến thư mục chứa file DICOM')
    parser.add_argument('--patient', '-p', help='ID bệnh nhân cần lọc')
    parser.add_argument('--output', '-o', help='Thư mục đầu ra cho kết quả phân loại')
    
    args = parser.parse_args()
    
    # Thư mục đầu ra mặc định
    output_dir = args.output if args.output else os.path.join(args.directory, "classified")
    
    # Quét và phân loại
    classification_results = scan_dicom_directory(args.directory, args.patient)
    
    # Lưu kết quả
    save_classification_results(classification_results, output_dir, args.patient)
    
    print(f"\nĐã phân loại thành công! Kết quả được lưu vào: {output_dir}")

if __name__ == "__main__":
    main()