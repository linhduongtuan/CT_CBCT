import os
import glob
import shutil
import pydicom
import argparse
import pandas as pd
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

def extract_patient_id_from_filename(filename):
    """Trích xuất ID bệnh nhân từ tên file"""
    parts = filename.split('.')
    if len(parts) > 1:
        # Cấu trúc tên file thường là: CT.25001565.Image...
        # hoặc RI.25001565.MV_...
        return parts[1]
    return None

def extract_dicom_info(file_path):
    """Trích xuất thông tin quan trọng từ file DICOM"""
    try:
        dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
        
        # Trích xuất ID bệnh nhân từ metadata hoặc tên file
        filename = os.path.basename(file_path)
        patient_id = getattr(dcm, 'PatientID', None)
        if not patient_id:
            patient_id = extract_patient_id_from_filename(filename)
        
        # Xác định loại file (CT hoặc CBCT)
        if filename.startswith("CT."):
            file_type = "CT"
        elif filename.startswith("RI."):
            file_type = "CBCT"
        else:
            # Dựa vào modality nếu không thể xác định từ tên file
            modality = getattr(dcm, 'Modality', 'Unknown')
            if modality == 'CT':
                file_type = "CT"
            elif modality in ['RTIMAGE', 'RI']:
                file_type = "CBCT"
            else:
                return None  # Bỏ qua nếu không phải CT hoặc CBCT
        
        # Trích xuất ngày chụp
        acquisition_date = None
        
        # Thử các trường ngày khác nhau
        if hasattr(dcm, 'AcquisitionDate'):
            acquisition_date = dcm.AcquisitionDate
        elif hasattr(dcm, 'ContentDate'):
            acquisition_date = dcm.ContentDate
        elif hasattr(dcm, 'SeriesDate'):
            acquisition_date = dcm.SeriesDate
        elif hasattr(dcm, 'StudyDate'):
            acquisition_date = dcm.StudyDate
        
        # Định dạng lại ngày
        if acquisition_date:
            try:
                # Định dạng DICOM: YYYYMMDD
                acquisition_date = f"{acquisition_date[:4]}-{acquisition_date[4:6]}-{acquisition_date[6:8]}"
            except:
                # Giữ nguyên nếu không thể định dạng
                pass
        else:
            # Nếu không tìm thấy ngày trong metadata, sử dụng phương pháp dự phòng
            # Thử trích xuất từ tên file hoặc đặt là "unknown_date"
            acquisition_date = "unknown_date"
        
        return {
            'path': file_path,
            'patient_id': patient_id,
            'file_type': file_type,
            'acquisition_date': acquisition_date,
            'filename': filename
        }
        
    except Exception as e:
        print(f"Lỗi khi đọc file {file_path}: {e}")
        return None

def process_file(file_path, output_dir, copy_files=True):
    """Xử lý một file DICOM và sắp xếp vào thư mục phù hợp"""
    info = extract_dicom_info(file_path)
    if not info:
        return False
    
    # Tạo đường dẫn đến thư mục đích
    patient_folder = os.path.join(output_dir, info['patient_id'])
    type_folder = os.path.join(patient_folder, info['file_type'])
    date_folder = os.path.join(type_folder, info['acquisition_date'])
    
    # Tạo thư mục nếu chưa tồn tại
    os.makedirs(date_folder, exist_ok=True)
    
    # Đường dẫn đến file đích
    dest_path = os.path.join(date_folder, info['filename'])
    
    # Sao chép hoặc tạo symbolic link
    if not os.path.exists(dest_path):
        if copy_files:
            shutil.copy2(file_path, dest_path)
        else:
            # Tạo symbolic link thay vì sao chép (tiết kiệm không gian)
            try:
                os.symlink(os.path.abspath(file_path), dest_path)
            except:
                # Nếu không tạo được symlink, sao chép file
                shutil.copy2(file_path, dest_path)
    
    return True

def organize_dicom_files(input_dir, output_dir, copy_files=True, max_workers=4):
    """Tổ chức lại các file DICOM theo bệnh nhân, loại và ngày"""
    print(f"Đang quét thư mục {input_dir} để tìm tất cả file DICOM...")
    
    # Tìm tất cả file DICOM trong thư mục đầu vào
    dicom_files = glob.glob(os.path.join(input_dir, "**/*.dcm"), recursive=True)
    total_files = len(dicom_files)
    
    if total_files == 0:
        print("Không tìm thấy file DICOM nào!")
        return
    
    print(f"Tìm thấy {total_files} file DICOM. Đang phân loại...")
    
    # Tạo thư mục đầu ra nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    
    # Xử lý song song để tăng tốc độ
    processed_count = 0
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Tạo các task xử lý
        future_to_file = {
            executor.submit(process_file, file_path, output_dir, copy_files): file_path 
            for file_path in dicom_files
        }
        
        # Theo dõi tiến độ
        for future in tqdm(as_completed(future_to_file), total=total_files, desc="Đang xử lý"):
            file_path = future_to_file[future]
            try:
                if future.result():
                    processed_count += 1
            except Exception as e:
                print(f"Lỗi khi xử lý {file_path}: {e}")
    
    print(f"\nĐã xử lý thành công {processed_count}/{total_files} file DICOM.")
    
    # Tạo báo cáo tổng hợp
    create_summary_report(output_dir)
    
    print(f"Các file đã được tổ chức vào thư mục: {output_dir}")

def create_summary_report(output_dir):
    """Tạo báo cáo tổng hợp về số lượng ảnh mỗi loại cho mỗi bệnh nhân"""
    print("Đang tạo báo cáo tổng hợp...")
    
    summary = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    
    # Quét thư mục đầu ra để đếm số lượng file
    for root, dirs, files in os.walk(output_dir):
        # Chỉ xử lý các thư mục chứa file DICOM
        if files and any(f.endswith('.dcm') for f in files):
            # Trích xuất thông tin thư mục
            rel_path = os.path.relpath(root, output_dir)
            parts = rel_path.split(os.sep)
            
            if len(parts) >= 3:  # patient_id/type/date
                patient_id = parts[0]
                file_type = parts[1]
                acq_date = parts[2]
                
                # Đếm số lượng file
                dicom_count = sum(1 for f in files if f.endswith('.dcm'))
                summary[patient_id][file_type][acq_date] = dicom_count
    
    # Tạo DataFrame từ dữ liệu tổng hợp
    rows = []
    for patient_id, types in summary.items():
        for file_type, dates in types.items():
            for acq_date, count in dates.items():
                rows.append({
                    'Patient ID': patient_id,
                    'Image Type': file_type,
                    'Acquisition Date': acq_date,
                    'File Count': count
                })
    
    # Tạo DataFrame và lưu thành file CSV
    if rows:
        df = pd.DataFrame(rows)
        summary_path = os.path.join(output_dir, "summary_report.csv")
        df.to_csv(summary_path, index=False)
        
        # Hiển thị thống kê tổng quan
        print("\nTổng hợp số lượng ảnh theo bệnh nhân:")
        patient_summary = df.groupby(['Patient ID', 'Image Type'])['File Count'].sum().unstack(fill_value=0)
        print(patient_summary)
        
        print(f"\nBáo cáo chi tiết đã được lưu vào: {summary_path}")

def main():
    parser = argparse.ArgumentParser(description='Phân loại ảnh CT và CBCT theo bệnh nhân và ngày điều trị')
    parser.add_argument('input_dir', help='Thư mục chứa các file DICOM')
    parser.add_argument('--output', '-o', default='organized_dicom', help='Thư mục đầu ra')
    parser.add_argument('--link', '-l', action='store_true', help='Tạo symbolic link thay vì sao chép file')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Số luồng xử lý song song')
    
    args = parser.parse_args()
    
    copy_files = not args.link
    action_type = "Sao chép" if copy_files else "Tạo liên kết tới"
    
    print(f"{action_type} các file DICOM từ {args.input_dir} đến {args.output}")
    
    organize_dicom_files(args.input_dir, args.output, copy_files, args.workers)

if __name__ == "__main__":
    main()