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
        
        # Xác định loại file từ tên file hoặc metadata
        file_type = None
        
        # Phát hiện loại file từ tiền tố tên file
        known_prefixes = {
            "CT": "CT",  # CT Image
            "RI": "RI",  # RT Image (CBCT, MV, kV)
            "RS": "RS",  # RT Structure Set
            "RE": "RE",  # RT Registration
            "RT": "RT",  # RT Plan
            "RD": "RD",  # RT Dose
        }
        
        # Kiểm tra tiền tố tên file
        for prefix, type_value in known_prefixes.items():
            if filename.startswith(prefix + "."):
                file_type = type_value
                break
        
        # Nếu không xác định được từ tên file, thử dựa vào modality và SOP Class
        if not file_type:
            modality = getattr(dcm, 'Modality', 'Unknown')
            sop_class = getattr(dcm, 'SOPClassUID', 'Unknown')
            
            # Ánh xạ modality/SOPClass sang loại file
            if modality == 'CT':
                file_type = "CT"
            elif modality == 'RTIMAGE':
                file_type = "RI"
            elif modality == 'RTSTRUCT':
                file_type = "RS"
            elif modality == 'REG':
                file_type = "RE"
            elif modality == 'RTPLAN':
                file_type = "RT"
            elif modality == 'RTDOSE':
                file_type = "RD"
            else:
                # Nếu không thể xác định loại file, đặt là "OTHER"
                file_type = "OTHER"
        
        # Kiểm tra xem có phải CBCT không
        is_cbct = False
        if "CBCT" in filename.upper() or "CONE" in filename.upper():
            is_cbct = True
        if file_type == "RI" and ("MV" in filename or "KV" in filename):
            is_cbct = True
            
        # Trích xuất ngày chụp
        acquisition_date = None
        
        # Thử các trường ngày khác nhau
        date_fields = [
            'AcquisitionDate',
            'ContentDate',
            'SeriesDate',
            'StudyDate',
            'InstanceCreationDate',
            'StructureSetDate',
            'PlanDate',
            'DoseReferenceSequence'
        ]
        
        for field in date_fields:
            if hasattr(dcm, field):
                date_value = getattr(dcm, field)
                if isinstance(date_value, str) and len(date_value) == 8:
                    acquisition_date = date_value
                    break
        
        # Định dạng lại ngày
        if acquisition_date:
            try:
                # Định dạng DICOM: YYYYMMDD
                acquisition_date = f"{acquisition_date[:4]}-{acquisition_date[4:6]}-{acquisition_date[6:8]}"
            except:
                # Giữ nguyên nếu không thể định dạng
                pass
        else:
            # Nếu không tìm thấy ngày trong metadata, thử trích xuất từ đường dẫn
            for part in file_path.split(os.sep):
                if len(part) == 10 and part.count('-') == 2:  # Định dạng YYYY-MM-DD
                    acquisition_date = part
                    break
            
            # Nếu vẫn không tìm thấy, đặt là "unknown_date"
            if not acquisition_date:
                acquisition_date = "unknown_date"
        
        # Lấy thêm thông tin bổ sung
        series_desc = getattr(dcm, 'SeriesDescription', '')
        if series_desc and ('CBCT' in series_desc.upper() or 'CONE' in series_desc.upper()):
            is_cbct = True
            
        return {
            'path': file_path,
            'patient_id': patient_id,
            'file_type': file_type,
            'is_cbct': is_cbct,
            'acquisition_date': acquisition_date,
            'filename': filename,
            'modality': getattr(dcm, 'Modality', 'Unknown'),
            'series_desc': series_desc
        }
        
    except Exception as e:
        print(f"Lỗi khi đọc file {file_path}: {e}")
        return None

# Phạm vi lớp này được định nghĩa ở mức top-level để có thể picklable
class PatientTreatmentInfo:
    def __init__(self):
        self.first_date = None  # Ngày đầu tiên của chu kỳ điều trị
        self.treatment_dates = set()  # Tất cả các ngày điều trị
        self.has_ct = False  # Có ảnh CT hay không
        self.has_cbct = False  # Có ảnh CBCT hay không
        self.ct_files = []  # Danh sách file CT
        self.cbct_files = []  # Danh sách file CBCT/RI

def determine_treatment_dates(input_dir):
    """Xác định ngày bắt đầu điều trị và các ngày điều trị tiếp theo cho mỗi bệnh nhân"""
    print("Xác định ngày điều trị cho mỗi bệnh nhân...")
    
    # Dictionary lưu trữ thông tin điều trị
    patient_treatment_info = {}
    
    # Tìm tất cả file DICOM
    dicom_files = glob.glob(os.path.join(input_dir, "**/*.dcm"), recursive=True)
    
    # Quét qua tất cả file để xác định ngày điều trị
    for file_path in tqdm(dicom_files, desc="Đang phân tích ngày điều trị"):
        info = extract_dicom_info(file_path)
        if not info or not info['patient_id'] or info['acquisition_date'] == 'unknown_date':
            continue
            
        patient_id = info['patient_id']
        date = info['acquisition_date']
        
        # Khởi tạo đối tượng thông tin nếu chưa có
        if patient_id not in patient_treatment_info:
            patient_treatment_info[patient_id] = PatientTreatmentInfo()
        
        # Thêm ngày vào tập các ngày điều trị
        patient_treatment_info[patient_id].treatment_dates.add(date)
        
        # Lưu thông tin file CT và CBCT/RI
        if info['file_type'] == 'CT' and not info['is_cbct']:
            patient_treatment_info[patient_id].has_ct = True
            patient_treatment_info[patient_id].ct_files.append((file_path, date))
        elif info['is_cbct'] or (info['file_type'] == 'RI' and ('MV' in info['filename'] or 'KV' in info['filename'])):
            patient_treatment_info[patient_id].has_cbct = True
            patient_treatment_info[patient_id].cbct_files.append((file_path, date))
    
    # Xác định ngày đầu tiên là ngày sớm nhất có ảnh CT
    for patient_id, info in patient_treatment_info.items():
        if info.has_ct:
            # Tìm ngày sớm nhất có ảnh CT
            ct_dates = {date for _, date in info.ct_files}
            if ct_dates:
                info.first_date = min(ct_dates)
        
        # Nếu không có ảnh CT, dùng ngày sớm nhất trong tất cả các ngày
        if not info.first_date and info.treatment_dates:
            info.first_date = min(info.treatment_dates)
    
    # Tạo dictionaries để sử dụng trong process_file
    first_dates = {}
    for patient_id, info in patient_treatment_info.items():
        if info.first_date:
            first_dates[patient_id] = info.first_date

    print(f"Đã xác định thông tin điều trị cho {len(patient_treatment_info)} bệnh nhân")
    return first_dates

def process_file(file_path, output_dir, copy_files, first_dates):
    """Xử lý một file DICOM và sắp xếp vào thư mục phù hợp"""
    info = extract_dicom_info(file_path)
    if not info:
        return False
    
    # Bỏ qua nếu không có ID bệnh nhân
    if not info['patient_id']:
        print(f"Bỏ qua file không có ID bệnh nhân: {file_path}")
        return False
    
    patient_id = info['patient_id']
    original_file_type = info['file_type']
    acquisition_date = info['acquisition_date']
    
    # Quy tắc phân loại file:
    # 1. CHỈ file tiền tố "CT" mới được di chuyển vào thư mục CBCT khi không phải ngày đầu tiên
    # 2. Các file tiền tố khác (RI, RS, RD, RE, RT) luôn giữ nguyên loại, bất kể ngày nào
    
    # Mặc định, giữ nguyên loại file
    file_type = original_file_type
    
    # Chỉ áp dụng quy tắc đặc biệt cho file CT
    if original_file_type == 'CT' and patient_id in first_dates:
        first_date = first_dates[patient_id]
        
        # Nếu KHÔNG phải ngày đầu tiên -> chuyển thành CBCT
        if acquisition_date != first_date:
            file_type = 'CBCT'
    
    # Tạo đường dẫn đến thư mục đích
    patient_folder = os.path.join(output_dir, patient_id)
    type_folder = os.path.join(patient_folder, file_type)
    date_folder = os.path.join(type_folder, acquisition_date)
    
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
            except Exception as e:
                print(f"Không thể tạo symlink cho {file_path}: {e}. Đang sao chép file...")
                # Nếu không tạo được symlink, sao chép file
                shutil.copy2(file_path, dest_path)
    
    return {
        'success': True,
        'patient_id': patient_id,
        'original_type': original_file_type,
        'assigned_type': file_type,
        'date': acquisition_date
    }

def process_files_sequentially(dicom_files, output_dir, copy_files, first_dates):
    """Xử lý các file theo tuần tự thay vì song song"""
    processed_count = 0
    failed_files = []
    results = []
    
    for file_path in tqdm(dicom_files, desc="Đang xử lý"):
        try:
            result = process_file(file_path, output_dir, copy_files, first_dates)
            if result and result.get('success', False):
                processed_count += 1
                results.append(result)
            else:
                failed_files.append(file_path)
        except Exception as e:
            print(f"Lỗi khi xử lý {file_path}: {e}")
            failed_files.append(file_path)
    
    return processed_count, failed_files, results

def organize_dicom_files(input_dir, output_dir, copy_files=True, max_workers=4):
    """Tổ chức lại các file DICOM theo bệnh nhân, loại và ngày"""
    print(f"Đang quét thư mục {input_dir} để tìm tất cả file DICOM...")
    
    # Xác định ngày điều trị cho mỗi bệnh nhân
    first_dates = determine_treatment_dates(input_dir)
    
    # Tìm tất cả file DICOM trong thư mục đầu vào
    dicom_files = glob.glob(os.path.join(input_dir, "**/*.dcm"), recursive=True)
    total_files = len(dicom_files)
    
    if total_files == 0:
        print("Không tìm thấy file DICOM nào!")
        return
    
    print(f"Tìm thấy {total_files} file DICOM. Đang phân loại...")
    
    # Tạo thư mục đầu ra nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    
    # Xử lý tuần tự thay vì song song để tránh lỗi pickle
    processed_count, failed_files, results = process_files_sequentially(
        dicom_files, output_dir, copy_files, first_dates
    )
    
    print(f"\nĐã xử lý thành công {processed_count}/{total_files} file DICOM.")
    
    # Thống kê kết quả phân loại
    type_conversion = defaultdict(int)
    for result in results:
        if result['original_type'] != result['assigned_type']:
            key = f"{result['original_type']} -> {result['assigned_type']}"
            type_conversion[key] += 1
    
    if type_conversion:
        print("\nThống kê chuyển đổi loại file:")
        for conversion, count in type_conversion.items():
            print(f"  {conversion}: {count} files")
    
    if failed_files:
        print(f"Số file thất bại: {len(failed_files)}")
        log_file = os.path.join(output_dir, "failed_files.log")
        with open(log_file, 'w') as f:
            for file_path in failed_files:
                f.write(f"{file_path}\n")
        print(f"Danh sách file thất bại được lưu tại: {log_file}")
    
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
        
        # Sắp xếp theo Patient ID và Image Type
        df = df.sort_values(['Patient ID', 'Image Type', 'Acquisition Date'])
        
        # Lưu báo cáo chi tiết
        summary_path = os.path.join(output_dir, "summary_report.csv")
        df.to_csv(summary_path, index=False)
        
        # Hiển thị thống kê tổng quan theo bệnh nhân và loại file
        patient_summary = df.groupby(['Patient ID', 'Image Type'])['File Count'].sum().unstack(fill_value=0)
        
        # Thêm cột tổng số file cho mỗi bệnh nhân
        if not patient_summary.empty:
            patient_summary['Total'] = patient_summary.sum(axis=1)
        
        # Lưu thống kê tổng quan
        overview_path = os.path.join(output_dir, "patient_overview.csv")
        patient_summary.to_csv(overview_path)
        
        print("\nTổng hợp số lượng ảnh theo bệnh nhân:")
        print(patient_summary)
        
        # Kiểm tra xem mỗi bệnh nhân có đúng 1 ngày trong thư mục CT hay không
        verification_df = df[df['Image Type'] == 'CT'].groupby('Patient ID')['Acquisition Date'].nunique()
        multi_ct_date_patients = verification_df[verification_df > 1].index.tolist()
        
        if multi_ct_date_patients:
            print("\nCẢNH BÁO: Các bệnh nhân có nhiều hơn một ngày chụp trong thư mục CT:")
            for pid in multi_ct_date_patients:
                dates = df[(df['Patient ID'] == pid) & (df['Image Type'] == 'CT')]['Acquisition Date'].unique()
                print(f"  - {pid}: {', '.join(dates)}")
        
        print(f"\nBáo cáo chi tiết đã được lưu vào: {summary_path}")
        print(f"Báo cáo tổng quan đã được lưu vào: {overview_path}")

def main():
    parser = argparse.ArgumentParser(description='Phân loại ảnh DICOM theo bệnh nhân, loại và ngày điều trị')
    parser.add_argument('input_dir', help='Thư mục chứa các file DICOM')
    parser.add_argument('--output', '-o', default='organized_dicom', help='Thư mục đầu ra')
    parser.add_argument('--link', '-l', action='store_true', help='Tạo symbolic link thay vì sao chép file')
    parser.add_argument('--workers', '-w', type=int, default=4, help='Số luồng xử lý song song')
    
    args = parser.parse_args()
    
    copy_files = not args.link
    action_type = "Sao chép" if copy_files else "Tạo liên kết tới"
    
    print(f"{action_type} các file DICOM từ {args.input_dir} đến {args.output}")
    
    start_time = datetime.now()
    organize_dicom_files(args.input_dir, args.output, copy_files, args.workers)
    end_time = datetime.now()
    
    elapsed_time = end_time - start_time
    print(f"Thời gian thực hiện: {elapsed_time}")

if __name__ == "__main__":
    main()
