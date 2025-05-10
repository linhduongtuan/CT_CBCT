#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script phát hiện và xử lý file DICOM trùng lặp - Sửa lỗi cho CBCT
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

def extract_base_name(filename):
    """
    Trích xuất tên cơ bản từ tên file, loại bỏ hậu tố số
    Ví dụ: "CT.25001565.Image 1.0004.dcm" -> "CT.25001565.Image 1"
    Đã sửa để xử lý đúng với các file trong CBCT
    """
    # Loại bỏ phần mở rộng
    base = os.path.splitext(filename)[0]
    
    # Tìm mẫu "Image X" hoặc "Field X" và giữ nguyên
    image_match = re.search(r'(Image\s+\d+)', base)
    field_match = re.search(r'(Field\s+\d+)', base)
    
    if image_match or field_match:
        # Giữ lại thông tin Image/Field số
        pattern = r'(\.+\d+)+$'
        return re.sub(pattern, '', base)
    else:
        # Xử lý các trường hợp khác
        pattern = r'(\.+\d+)+$'
        return re.sub(pattern, '', base)

def extract_image_number(filename):
    """
    Trích xuất số Image từ tên file DICOM
    Ví dụ: "CT.25001565.Image 1.0004.dcm" -> "1"
    """
    # Tìm số Image trong tên file
    match = re.search(r'Image\s+(\d+)', filename)
    if match:
        return int(match.group(1))
    
    # Tìm số Field trong tên file
    match = re.search(r'Field\s+(\d+)', filename)
    if match:
        return int(match.group(1))
    
    # Nếu không có mẫu đặc biệt, trả về -1
    return -1

def get_patient_id(filename):
    """
    Trích xuất ID bệnh nhân từ tên file
    Ví dụ: "CT.25001565.Image 1.0004.dcm" -> "25001565"
    """
    parts = filename.split('.')
    if len(parts) > 1:
        return parts[1]
    return "unknown"

def should_ignore_cbct(root_dir):
    """
    Kiểm tra xem có nên bỏ qua thư mục CBCT không
    Trả về True nếu các file CBCT không nên được xem là trùng lặp
    """
    return True  # Luôn bỏ qua thư mục CBCT để không xem là trùng lặp

def process_duplicates(root_dir, output_dir, action='report', verbose=True):
    """
    Xử lý các file DICOM trùng lặp
    
    Tham số:
    - root_dir: Thư mục gốc chứa các file đã phân loại
    - output_dir: Thư mục lưu báo cáo và file trùng lặp
    - action: Hành động xử lý ('report', 'move')
    - verbose: Hiển thị thông tin chi tiết
    
    Trả về:
    - Đường dẫn đến báo cáo
    """
    if verbose:
        print(f"Đang quét {root_dir} để tìm file DICOM trùng lặp...")
    
    # Tạo thư mục output nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Đếm số file đã quét và xử lý
    total_scanned = 0
    total_duplicates = 0
    total_kept = 0
    total_processed = 0
    
    # Biến lưu trữ thông tin báo cáo
    report_rows = []
    
    # Duyệt qua tất cả thư mục bệnh nhân
    patient_dirs = [d for d in os.listdir(root_dir) if os.path.isdir(os.path.join(root_dir, d))]
    
    if verbose:
        print(f"Tìm thấy {len(patient_dirs)} thư mục bệnh nhân")
    
    for patient_dir in tqdm(patient_dirs, desc="Xử lý từng bệnh nhân"):
        patient_path = os.path.join(root_dir, patient_dir)
        
        # Kiểm tra từng loại thư mục (CT, CBCT, etc.)
        for folder_type in os.listdir(patient_path):
            folder_type_path = os.path.join(patient_path, folder_type)
            
            # Chỉ xử lý thư mục
            if not os.path.isdir(folder_type_path):
                continue
            
            # Bỏ qua thư mục CBCT
            if folder_type == 'CBCT' and should_ignore_cbct(root_dir):
                if verbose:
                    print(f"Bỏ qua thư mục CBCT cho bệnh nhân {patient_dir} (không xem là trùng lặp)")
                continue
            
            # Chỉ xử lý thư mục CT
            if folder_type != 'CT':
                if verbose:
                    print(f"Bỏ qua thư mục {folder_type} cho bệnh nhân {patient_dir} (chỉ xử lý CT)")
                continue
            
            # Duyệt qua các thư mục ngày
            for date_folder in os.listdir(folder_type_path):
                date_path = os.path.join(folder_type_path, date_folder)
                if not os.path.isdir(date_path):
                    continue
                
                # Lấy tất cả file DICOM trong thư mục ngày
                dicom_files = glob.glob(os.path.join(date_path, "*.dcm"))
                total_scanned += len(dicom_files)
                
                if not dicom_files:
                    continue
                
                # Nhóm file theo image_base_name (không bao gồm hậu tố số)
                image_groups = defaultdict(list)
                
                for file_path in dicom_files:
                    filename = os.path.basename(file_path)
                    base_name = extract_base_name(filename)
                    image_groups[base_name].append(file_path)
                
                # Loại bỏ các nhóm chỉ có 1 file (không trùng lặp)
                duplicate_groups = {k: v for k, v in image_groups.items() if len(v) > 1}
                
                # Xử lý từng nhóm trùng lặp
                for base_name, files in duplicate_groups.items():
                    # Đếm số lượng trùng lặp
                    total_duplicates += len(files) - 1
                    total_kept += 1
                    
                    # Sắp xếp theo kích thước tăng dần (ưu tiên file nhỏ hơn cho CT)
                    sorted_files = sorted(files, key=os.path.getsize)
                    
                    # File đầu tiên là file nhỏ nhất, giữ lại
                    best_file = sorted_files[0]
                    
                    # Thêm thông tin file giữ lại vào báo cáo
                    report_rows.append({
                        'Patient ID': patient_dir,
                        'Folder Type': folder_type,
                        'Date': date_folder,
                        'Base Name': base_name,
                        'File Path': best_file,
                        'File Size (KB)': round(os.path.getsize(best_file) / 1024, 2),
                        'Action': 'Keep',
                        'Is Best Match': True
                    })
                    
                    # Xử lý các file còn lại (trùng lặp)
                    for file_path in sorted_files[1:]:
                        # Thêm thông tin vào báo cáo
                        report_rows.append({
                            'Patient ID': patient_dir,
                            'Folder Type': folder_type,
                            'Date': date_folder,
                            'Base Name': base_name,
                            'File Path': file_path,
                            'File Size (KB)': round(os.path.getsize(file_path) / 1024, 2),
                            'Action': action.capitalize(),
                            'Is Best Match': False
                        })
                        
                        # Thực hiện di chuyển nếu action là 'move'
                        if action == 'move':
                            try:
                                # Tạo thư mục duplicates
                                duplicate_dir = os.path.join(output_dir, 'duplicates')
                                os.makedirs(duplicate_dir, exist_ok=True)
                                
                                # Tạo thư mục con tương ứng với cấu trúc ban đầu
                                rel_path = os.path.relpath(file_path, root_dir)
                                dest_path = os.path.join(duplicate_dir, rel_path)
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                
                                # Di chuyển file
                                shutil.move(file_path, dest_path)
                                total_processed += 1
                            except Exception as e:
                                if verbose:
                                    print(f"Lỗi khi di chuyển file {file_path}: {e}")
    
    # Tạo DataFrame và lưu báo cáo
    if report_rows:
        report_df = pd.DataFrame(report_rows)
        report_path = os.path.join(output_dir, f'ct_duplicate_report_{timestamp}.xlsx')
        report_df.to_excel(report_path, index=False)
        
        if verbose:
            print(f"\nĐã tạo báo cáo file trùng lặp: {report_path}")
    else:
        report_path = None
        if verbose:
            print("\nKhông tìm thấy file trùng lặp nào.")
    
    # Tạo báo cáo tổng hợp
    summary = {
        'Total Scanned Files': total_scanned,
        'Duplicate Groups': total_kept,
        'Total Duplicates': total_duplicates,
        'Files To Keep': total_kept,
        'Files Processed': total_processed if action == 'move' else 0
    }
    
    summary_df = pd.DataFrame([summary])
    summary_path = os.path.join(output_dir, f'duplicate_summary_{timestamp}.csv')
    summary_df.to_csv(summary_path, index=False)
    
    if verbose:
        print("\nTổng kết:")
        for key, value in summary.items():
            print(f"- {key}: {value}")
        print(f"Đã lưu báo cáo tổng hợp vào: {summary_path}")
        
        if action == 'move' and total_processed > 0:
            print(f"Đã di chuyển {total_processed} file trùng lặp vào: {os.path.join(output_dir, 'duplicates')}")
    
    return report_path

def main():
    parser = argparse.ArgumentParser(description='Phát hiện và xử lý file DICOM trùng lặp - Chỉ xử lý thư mục CT')
    parser.add_argument('input_dir', help='Thư mục chứa các file DICOM đã phân loại')
    parser.add_argument('--output', '-o', default='duplicate_reports', help='Thư mục lưu báo cáo và file trùng lặp')
    parser.add_argument('--action', '-a', choices=['report', 'move'], default='report',
                        help='Hành động xử lý (report: chỉ báo cáo, move: di chuyển)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Không hiển thị thông tin chi tiết')
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    
    if not args.quiet:
        print(f"Bắt đầu phát hiện và xử lý file trùng lặp từ: {args.input_dir}")
        print(f"Hành động: {args.action}")
        print(f"LƯU Ý: Chỉ xử lý các file trong thư mục CT, bỏ qua hoàn toàn CBCT và các thư mục khác.")
    
    # Xử lý các file trùng lặp
    process_duplicates(
        args.input_dir, 
        args.output, 
        action=args.action, 
        verbose=not args.quiet
    )
    
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    
    if not args.quiet:
        print(f"\nThời gian thực hiện: {elapsed_time}")

if __name__ == "__main__":
    main()
