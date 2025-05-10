#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script phát hiện và xử lý file DICOM trùng lặp - Chỉ xử lý thư mục CT
"""

import os
import glob
import pydicom
import hashlib
import argparse
import pandas as pd
from collections import defaultdict
from datetime import datetime
from tqdm import tqdm
import shutil
import re
import logging

# Thiết lập logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def extract_base_name(filename):
    """
    Trích xuất tên cơ bản từ tên file, loại bỏ hậu tố số
    Ví dụ: "CT.25001565.Image 1.0004.dcm" -> "CT.25001565.Image 1"
    """
    # Loại bỏ phần mở rộng
    base = os.path.splitext(filename)[0]
    
    # Cải tiến pattern để nhận diện chính xác hơn
    # Loại bỏ tất cả các hậu tố số ở cuối tên file
    pattern = r'(\.+\d+)+$'
    return re.sub(pattern, '', base)

def get_file_size(file_path):
    """Lấy kích thước file theo KB"""
    try:
        return os.path.getsize(file_path) / 1024  # Đổi sang KB
    except:
        return 0

def extract_patient_folders(root_dir):
    """Lấy tất cả thư mục bệnh nhân trong thư mục gốc"""
    patient_folders = []
    
    # Lấy tất cả mục trực tiếp trong thư mục gốc
    for item in os.listdir(root_dir):
        item_path = os.path.join(root_dir, item)
        if os.path.isdir(item_path):
            patient_folders.append(item_path)
    
    return patient_folders

def process_ct_duplicates(root_dir, output_dir, action='report', verbose=True):
    """
    Xử lý file trùng lặp CHỈ trong thư mục CT
    
    Tham số:
    - root_dir: Thư mục gốc chứa các file đã phân loại
    - output_dir: Thư mục lưu báo cáo và file trùng lặp
    - action: Hành động xử lý ('report', 'move', 'delete')
    - verbose: Hiển thị thông tin chi tiết
    """
    # Tạo thư mục output nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    
    # Timestamp cho tên file báo cáo
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Sẵn sàng các biến thống kê
    all_report_rows = []
    total_processed = 0
    total_kept = 0
    total_to_process = 0
    total_ct_files = 0
    
    # Tạo thư mục duplicates nếu cần di chuyển file
    duplicate_dir = os.path.join(output_dir, 'duplicates')
    if action == 'move':
        os.makedirs(duplicate_dir, exist_ok=True)
    
    # Lấy danh sách thư mục bệnh nhân
    patient_folders = extract_patient_folders(root_dir)
    
    if verbose:
        print(f"Tìm thấy {len(patient_folders)} thư mục bệnh nhân trong thư mục gốc.")
        print("Chỉ xử lý trùng lặp trong thư mục CT, bỏ qua tất cả các loại thư mục khác.")
    
    # Xử lý từng thư mục bệnh nhân
    for patient_folder in tqdm(patient_folders, desc="Đang xử lý từng bệnh nhân"):
        patient_id = os.path.basename(patient_folder)
        
        # Kiểm tra xem có thư mục CT không
        ct_folder_path = os.path.join(patient_folder, "CT")
        if not (os.path.exists(ct_folder_path) and os.path.isdir(ct_folder_path)):
            continue
        
        # Nhóm file DICOM theo ngày trong thư mục CT
        date_folders = {}
        for date_folder in os.listdir(ct_folder_path):
            date_path = os.path.join(ct_folder_path, date_folder)
            if os.path.isdir(date_path):
                date_folders[date_folder] = date_path
        
        # Xử lý từng thư mục ngày, tìm trùng lặp trong mỗi ngày
        for date, date_path in date_folders.items():
            # Lấy tất cả file DICOM trong thư mục ngày
            dicom_files = glob.glob(os.path.join(date_path, "*.dcm"))
            
            if not dicom_files:
                continue
            
            total_ct_files += len(dicom_files)
            
            # Nhóm các file có tên cơ bản giống nhau
            base_name_groups = defaultdict(list)
            for file_path in dicom_files:
                file_name = os.path.basename(file_path)
                base_name = extract_base_name(file_name)
                base_name_groups[base_name].append(file_path)
            
            # Chỉ giữ lại các nhóm có nhiều hơn 1 file (thực sự trùng lặp)
            duplicate_groups = {k: v for k, v in base_name_groups.items() if len(v) > 1}
            
            if not duplicate_groups:
                continue
            
            # Xử lý từng nhóm trùng lặp
            for base_name, files in duplicate_groups.items():
                # CT - ưu tiên file nhỏ (sắp xếp tăng dần theo dung lượng)
                ranked_files = sorted(files, key=lambda f: get_file_size(f))
                
                # File đầu tiên là file tốt nhất, giữ lại
                best_file = ranked_files[0]
                files_to_process = ranked_files[1:]
                
                # Thêm vào báo cáo
                all_report_rows.append({
                    'Patient ID': patient_id,
                    'Date': date,
                    'Base Name': base_name,
                    'File Path': best_file,
                    'File Size (KB)': round(get_file_size(best_file), 2),
                    'Action': 'Keep',
                    'Is Best Match': True
                })
                
                total_kept += 1
                
                # Xử lý các file còn lại (trùng lặp)
                for file_path in files_to_process:
                    all_report_rows.append({
                        'Patient ID': patient_id,
                        'Date': date,
                        'Base Name': base_name,
                        'File Path': file_path,
                        'File Size (KB)': round(get_file_size(file_path), 2),
                        'Action': action.capitalize(),
                        'Is Best Match': False
                    })
                    
                    total_to_process += 1
                    
                    # Thực hiện hành động nếu không phải "report"
                    if action in ['move', 'delete']:
                        try:
                            if action == 'move':
                                # Tạo thư mục con tương ứng với cấu trúc ban đầu
                                rel_path = os.path.relpath(file_path, root_dir)
                                dest_path = os.path.join(duplicate_dir, rel_path)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                
                                # Di chuyển file
                                shutil.move(file_path, dest_path)
                            else:  # action == 'delete'
                                os.remove(file_path)
                            
                            total_processed += 1
                        except Exception as e:
                            error_msg = f"Lỗi khi {action} file {file_path}: {e}"
                            if verbose:
                                print(error_msg)
                            logger.error(error_msg)
    
    # Tạo DataFrame và lưu báo cáo
    if all_report_rows:
        report_df = pd.DataFrame(all_report_rows)
        report_path = os.path.join(output_dir, f'ct_duplicate_report_{timestamp}.xlsx')
        report_df.to_excel(report_path, index=False)
        
        if verbose:
            print(f"\nĐã tạo báo cáo file trùng lặp trong thư mục CT: {report_path}")
    
    # Tạo báo cáo tổng hợp
    summary = {
        'Total CT Files': total_ct_files,
        'Total Duplicate Groups': total_kept,
        'Files To Keep': total_kept,
        'Files To Process': total_to_process,
        'Files Processed': total_processed,
    }
    
    summary_df = pd.DataFrame([summary])
    summary_path = os.path.join(output_dir, f'ct_duplicate_summary_{timestamp}.csv')
    summary_df.to_csv(summary_path, index=False)
    
    if verbose:
        print("\nTổng kết:")
        for key, value in summary.items():
            print(f"- {key}: {value}")
        print(f"Đã lưu báo cáo tổng hợp vào: {summary_path}")
    
    return summary

def main():
    parser = argparse.ArgumentParser(description='Phát hiện và xử lý file DICOM trùng lặp - Chỉ xử lý thư mục CT')
    parser.add_argument('input_dir', help='Thư mục chứa các file DICOM đã phân loại')
    parser.add_argument('--output', '-o', default='duplicate_reports', help='Thư mục lưu báo cáo và file trùng lặp')
    parser.add_argument('--action', '-a', choices=['report', 'move', 'delete'], default='report',
                        help='Hành động xử lý (report: chỉ báo cáo, move: di chuyển, delete: xóa)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Không hiển thị thông tin chi tiết')
    parser.add_argument('--log', '-l', default='ct_duplicate_detection.log', help='File lưu log')
    
    args = parser.parse_args()
    
    # Thiết lập file log
    log_path = os.path.join(args.output, args.log)
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    file_handler = logging.FileHandler(log_path)
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(file_handler)
    
    start_time = datetime.now()
    
    if not args.quiet:
        print(f"Bắt đầu phát hiện và xử lý file trùng lặp từ: {args.input_dir}")
        print(f"Hành động: {args.action}")
        print(f"QUAN TRỌNG: Chỉ xử lý trùng lặp TRONG THƯ MỤC CT, không ảnh hưởng đến các thư mục khác.")
    
    # Xử lý các file trùng lặp
    process_ct_duplicates(
        args.input_dir, 
        args.output, 
        action=args.action, 
        verbose=not args.quiet
    )
    
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    
    if not args.quiet:
        print(f"\nThời gian thực hiện: {elapsed_time}")
        print(f"Đã lưu log tại: {log_path}")

if __name__ == "__main__":
    main()
