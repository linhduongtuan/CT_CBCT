#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script phát hiện và xử lý file DICOM trùng lặp - Phiên bản thông minh
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
    """
    # Loại bỏ phần mở rộng
    base = os.path.splitext(filename)[0]
    
    # Cải tiến pattern để nhận diện chính xác hơn
    # Loại bỏ tất cả các hậu tố số ở cuối tên file
    pattern = r'(\.+\d+)+$'
    return re.sub(pattern, '', base)

def extract_series_info(filename):
    """
    Trích xuất thông tin chuỗi ảnh từ tên file
    Ví dụ: "CT.25001565.Image 1.0013.dcm" -> "CT.25001565.Image 1"
    """
    # Tìm pattern cụ thể cho tên file DICOM 
    match = re.match(r'^([A-Z]+\.\d+\.Image\s+\d+)', filename)
    if match:
        return match.group(1)
    
    # Tìm pattern khác (ví dụ: CT.25001565.Field 5.dcm)
    match = re.match(r'^([A-Z]+\.\d+\.[^\.]+)', filename)
    if match:
        return match.group(1)
        
    # Fallback: Chỉ lấy phần trước hậu tố số cuối cùng
    parts = re.split(r'\.\d+\.', filename)
    if len(parts) > 1:
        return parts[0]
    
    # Nếu không khớp pattern, trả về tên không có phần mở rộng
    return os.path.splitext(filename)[0]

def get_file_hash(file_path, block_size=65536):
    """
    Tính toán hash của file để so sánh nội dung
    """
    hasher = hashlib.md5()
    with open(file_path, 'rb') as f:
        buf = f.read(block_size)
        while len(buf) > 0:
            hasher.update(buf)
            buf = f.read(block_size)
    return hasher.hexdigest()

def extract_image_hash(file_path):
    """
    Trích xuất hash chỉ của dữ liệu hình ảnh (bỏ qua metadata)
    """
    try:
        dcm = pydicom.dcmread(file_path)
        if hasattr(dcm, 'PixelData'):
            hasher = hashlib.md5()
            hasher.update(dcm.PixelData)
            return hasher.hexdigest()
    except:
        pass
    return None

def get_image_resolution(file_path):
    """
    Trích xuất độ phân giải hình ảnh
    """
    try:
        dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
        if hasattr(dcm, 'Rows') and hasattr(dcm, 'Columns'):
            return dcm.Rows * dcm.Columns
    except:
        pass
    return 0

def get_dicom_key_attributes(dcm):
    """
    Lấy các thuộc tính quan trọng từ file DICOM để so sánh
    """
    attributes = {}
    
    # Các thuộc tính quan trọng để xác định trùng lặp
    key_attrs = [
        'SOPInstanceUID',
        'SeriesInstanceUID',
        'StudyInstanceUID',
        'InstanceNumber',
        'ImagePositionPatient',
        'AcquisitionTime',
        'ContentTime',
        'Rows',
        'Columns',
        'BitsAllocated'
    ]
    
    for attr in key_attrs:
        if hasattr(dcm, attr):
            attributes[attr] = getattr(dcm, attr)
    
    return attributes

def find_duplicate_files(root_dir, hash_method='advanced', verbose=True):
    """
    Tìm tất cả các file DICOM trùng lặp
    
    Tham số:
    - root_dir: Thư mục gốc chứa các file đã phân loại
    - hash_method: Phương pháp phát hiện ('filename', 'metadata', 'content', 'advanced', 'pattern')
    - verbose: Hiển thị thông tin chi tiết
    
    Trả về:
    - Dictionary chứa thông tin về các file trùng lặp
    """
    if verbose:
        print(f"Đang quét {root_dir} để tìm file DICOM trùng lặp...")
    
    # Tìm tất cả file DICOM
    dicom_files = glob.glob(os.path.join(root_dir, "**/*.dcm"), recursive=True)
    
    if verbose:
        print(f"Tìm thấy {len(dicom_files)} file DICOM. Đang phân tích...")
    
    duplicates = defaultdict(list)
    processed_files = 0
    error_files = []
    
    # Tùy thuộc vào phương pháp phát hiện
    if hash_method == 'filename':
        # Phương pháp 1: Dựa vào tên file cơ bản
        for file_path in tqdm(dicom_files, desc="Đang phân tích tên file"):
            filename = os.path.basename(file_path)
            base_name = extract_base_name(filename)
            duplicates[base_name].append(file_path)
            processed_files += 1
    
    elif hash_method == 'pattern':
        # Phương pháp mới: Dựa vào pattern tên file
        for file_path in tqdm(dicom_files, desc="Đang phân tích pattern tên file"):
            filename = os.path.basename(file_path)
            series_info = extract_series_info(filename)
            duplicates[series_info].append(file_path)
            processed_files += 1
    
    elif hash_method == 'metadata':
        # Phương pháp 2: Dựa vào metadata DICOM
        for file_path in tqdm(dicom_files, desc="Đang phân tích metadata DICOM"):
            try:
                dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                
                # Sử dụng SOPInstanceUID làm khóa chính
                if hasattr(dcm, 'SOPInstanceUID'):
                    key = dcm.SOPInstanceUID
                    duplicates[key].append(file_path)
                else:
                    # Backup: Sử dụng SeriesInstanceUID + InstanceNumber nếu có
                    if hasattr(dcm, 'SeriesInstanceUID') and hasattr(dcm, 'InstanceNumber'):
                        key = f"{dcm.SeriesInstanceUID}_{dcm.InstanceNumber}"
                        duplicates[key].append(file_path)
                    else:
                        # Fallback: Sử dụng tên file cơ bản
                        filename = os.path.basename(file_path)
                        base_name = extract_base_name(filename)
                        duplicates[base_name].append(file_path)
                
                processed_files += 1
            except Exception as e:
                error_files.append((file_path, str(e)))
                continue
    
    elif hash_method == 'content':
        # Phương pháp 3: Dựa vào nội dung file (MD5 hash)
        for file_path in tqdm(dicom_files, desc="Đang tính toán hash file"):
            try:
                file_hash = get_file_hash(file_path)
                duplicates[file_hash].append(file_path)
                processed_files += 1
            except Exception as e:
                error_files.append((file_path, str(e)))
                continue
    
    elif hash_method == 'advanced':
        # Phương pháp kết hợp: Dựa vào pattern tên file + thông tin cơ bản
        patient_groups = defaultdict(list)
        
        # Phân nhóm các file theo bệnh nhân để giảm scope so sánh
        for file_path in tqdm(dicom_files, desc="Đang nhóm file theo bệnh nhân"):
            filename = os.path.basename(file_path)
            parts = filename.split('.')
            if len(parts) > 1:
                patient_id = parts[1]  # Lấy phần PatientID từ tên file
                patient_groups[patient_id].append(file_path)
            else:
                # Không theo pattern, nhóm vào 'unknown'
                patient_groups['unknown'].append(file_path)
        
        # Xử lý từng nhóm bệnh nhân
        for patient_id, files in tqdm(patient_groups.items(), desc="Đang phân tích theo bệnh nhân"):
            # Tạo dict ánh xạ series info đến danh sách file
            series_files = defaultdict(list)
            
            for file_path in files:
                filename = os.path.basename(file_path)
                series_info = extract_series_info(filename)
                series_files[series_info].append(file_path)
            
            # Thêm vào kết quả chung
            for series_info, series_file_list in series_files.items():
                key = f"{patient_id}_{series_info}"
                duplicates[key].extend(series_file_list)
                processed_files += len(series_file_list)
    
    # Lọc ra chỉ giữ lại các nhóm có nhiều hơn 1 file (thực sự trùng lặp)
    true_duplicates = {key: files for key, files in duplicates.items() if len(files) > 1}
    
    if verbose:
        print(f"\nĐã phân tích {processed_files}/{len(dicom_files)} file DICOM.")
        print(f"Phát hiện {len(true_duplicates)} nhóm file trùng lặp với tổng số {sum(len(files) for files in true_duplicates.values())} file.")
        
        if error_files:
            print(f"Có {len(error_files)} file gặp lỗi khi phân tích.")
    
    return true_duplicates, error_files

def rank_duplicate_files(duplicate_files):
    """
    Xếp hạng các file trùng lặp để quyết định file nào giữ lại
    Quy tắc xếp hạng: 
    1. Ưu tiên khác nhau cho từng loại thư mục:
       - Thư mục CT: Ưu tiên file có dung lượng NHỎ hơn
       - Thư mục CBCT: Ưu tiên file có dung lượng LỚN hơn
    2. Ưu tiên file ở thư mục chính (CT, RI, RS) hơn là thư mục phụ (CBCT)
    3. Ưu tiên file có ít hậu tố số
    """
    ranked_duplicates = {}
    
    for key, files in duplicate_files.items():
        ranked_files = []
        
        # Phân loại file theo thư mục
        ct_files = []
        cbct_files = []
        other_files = []
        
        for file_path in files:
            folder_path = os.path.dirname(file_path)
            normalized_path = folder_path.replace('\\', '/')
            
            if '/CT/' in normalized_path:
                ct_files.append(file_path)
            elif '/CBCT/' in normalized_path:
                cbct_files.append(file_path)
            else:
                other_files.append(file_path)
        
        # Xếp hạng từng nhóm file
        for file_path in files:
            # Lấy thông tin cơ bản
            file_size = os.path.getsize(file_path)
            folder_path = os.path.dirname(file_path)
            normalized_path = folder_path.replace('\\', '/')
            file_name = os.path.basename(file_path)
            
            # Đếm số hậu tố
            suffix_count = len(re.findall(r'\.\d+', file_name))
            
            # Kiểm tra loại thư mục
            folder_priority = 10  # Mặc định
            is_ct_folder = False
            size_score = 0
            
            if '/CT/' in normalized_path:
                folder_priority = 1
                is_ct_folder = True
                # Đối với CT, ưu tiên file nhỏ hơn (âm điểm số)
                size_score = -file_size
            elif '/RI/' in normalized_path:
                folder_priority = 2
                # Đối với RI, ưu tiên file lớn hơn
                size_score = file_size
            elif '/RS/' in normalized_path:
                folder_priority = 3
                size_score = file_size
            elif '/RT/' in normalized_path:
                folder_priority = 4
                size_score = file_size
            elif '/RD/' in normalized_path:
                folder_priority = 5
                size_score = file_size
            elif '/RE/' in normalized_path:
                folder_priority = 6
                size_score = file_size
            elif '/CBCT/' in normalized_path:
                folder_priority = 7
                # Đối với CBCT, ưu tiên file lớn hơn
                size_score = file_size
            
            # Kiểm tra độ phân giải (chỉ cho CBCT hoặc loại khác ngoài CT)
            resolution_score = 0
            if not is_ct_folder:
                resolution = get_image_resolution(file_path)
                resolution_score = resolution
            
            # Tính điểm tổng, với CT thì ưu tiên file nhỏ hơn
            final_score = size_score - (suffix_count * 1000) - (folder_priority * 10000) + resolution_score
            
            ranked_files.append({
                'path': file_path,
                'size': file_size,
                'folder_priority': folder_priority,
                'suffix_count': suffix_count,
                'is_ct_folder': is_ct_folder,
                'resolution': resolution_score,
                'size_score': size_score,
                'score': final_score
            })
        
        # Sắp xếp theo điểm số giảm dần
        ranked_files.sort(key=lambda x: x['score'], reverse=True)
        ranked_duplicates[key] = ranked_files
    
    return ranked_duplicates

def process_duplicates(root_dir, output_dir, hash_method='advanced', action='report', verbose=True):
    """
    Xử lý các file DICOM trùng lặp
    
    Tham số:
    - root_dir: Thư mục gốc chứa các file đã phân loại
    - output_dir: Thư mục lưu báo cáo và file trùng lặp
    - hash_method: Phương pháp phát hiện ('filename', 'metadata', 'content', 'advanced', 'pattern')
    - action: Hành động xử lý ('report', 'move', 'delete')
    - verbose: Hiển thị thông tin chi tiết
    
    Trả về:
    - Đường dẫn đến báo cáo
    """
    # Tìm các file trùng lặp
    original_duplicates, error_files = find_duplicate_files(root_dir, hash_method, verbose)
    
    # Lưu thông tin tổng số file và nhóm để sử dụng sau này
    total_files = sum(len(files) for files in original_duplicates.values())
    total_groups = len(original_duplicates)
    total_duplicates = sum(len(files) - 1 for files in original_duplicates.values())
    
    # Xếp hạng các file trùng lặp
    ranked_duplicates = rank_duplicate_files(original_duplicates)
    
    # Tạo thư mục output nếu chưa tồn tại
    os.makedirs(output_dir, exist_ok=True)
    
    # Lưu thông tin các file gặp lỗi
    if error_files:
        error_df = pd.DataFrame(error_files, columns=['File Path', 'Error'])
        error_path = os.path.join(output_dir, 'error_files.csv')
        error_df.to_csv(error_path, index=False)
        if verbose:
            print(f"Đã lưu thông tin các file lỗi vào: {error_path}")
    
    # Tạo báo cáo
    report_rows = []
    
    for key, ranked_files in ranked_duplicates.items():
        best_file = ranked_files[0]
        
        for i, file_info in enumerate(ranked_files):
            report_rows.append({
                'Group Key': key,
                'File Path': file_info['path'],
                'File Size (KB)': round(file_info['size'] / 1024, 2),
                'Is CT Folder': file_info['is_ct_folder'],
                'Folder Priority': file_info['folder_priority'],
                'Suffix Count': file_info['suffix_count'],
                'Resolution Score': file_info['resolution'],
                'Size Score': file_info['size_score'],
                'Final Score': file_info['score'],
                'Is Best Match': i == 0,
                'Action': 'Keep' if i == 0 else action.capitalize()
            })
    
    # Tạo DataFrame và lưu báo cáo
    report_df = pd.DataFrame(report_rows)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = os.path.join(output_dir, f'duplicate_report_{timestamp}.xlsx')
    report_df.to_excel(report_path, index=False)
    
    if verbose:
        print(f"\nĐã tạo báo cáo file trùng lặp: {report_path}")
    
    # Thực hiện hành động với các file trùng lặp
    processed_count = 0
    
    if action in ['move', 'delete']:
        duplicate_dir = os.path.join(output_dir, 'duplicates')
        if action == 'move':
            os.makedirs(duplicate_dir, exist_ok=True)
        
        for key, ranked_files in tqdm(ranked_duplicates.items(), desc=f"Đang {action} file trùng lặp"):
            # Bỏ qua file đầu tiên (file tốt nhất)
            duplicate_files = [file_info['path'] for file_info in ranked_files[1:]]
            
            for file_path in duplicate_files:
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
                    
                    processed_count += 1
                except Exception as e:
                    if verbose:
                        print(f"Lỗi khi {action} file {file_path}: {e}")
        
        if verbose:
            if action == 'move':
                print(f"Đã di chuyển {processed_count} file trùng lặp vào: {duplicate_dir}")
            else:
                print(f"Đã xóa {processed_count} file trùng lặp")
    
    # Tạo báo cáo tổng hợp - SỬA LỖI: dùng giá trị đã lưu trước đó
    summary = {
        'Total Scan Files': total_files,
        'Duplicate Groups': total_groups,
        'Total Duplicates': total_duplicates,
        'Files To Keep': total_groups,
        'Files Processed': processed_count,
        'Error Files': len(error_files)
    }
    
    summary_df = pd.DataFrame([summary])
    summary_path = os.path.join(output_dir, f'duplicate_summary_{timestamp}.csv')
    summary_df.to_csv(summary_path, index=False)
    
    if verbose:
        print("\nTổng kết:")
        for key, value in summary.items():
            print(f"- {key}: {value}")
        print(f"Đã lưu báo cáo tổng hợp vào: {summary_path}")
    
    return report_path, summary

def main():
    parser = argparse.ArgumentParser(description='Phát hiện và xử lý file DICOM trùng lặp')
    parser.add_argument('input_dir', help='Thư mục chứa các file DICOM đã phân loại')
    parser.add_argument('--output', '-o', default='duplicate_reports', help='Thư mục lưu báo cáo và file trùng lặp')
    parser.add_argument('--method', '-m', 
                      choices=['filename', 'metadata', 'content', 'advanced', 'pattern'], 
                      default='advanced',
                      help='Phương pháp phát hiện trùng lặp (filename, metadata, content, advanced, pattern)')
    parser.add_argument('--action', '-a', choices=['report', 'move', 'delete'], default='report',
                        help='Hành động xử lý (report: chỉ báo cáo, move: di chuyển, delete: xóa)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Không hiển thị thông tin chi tiết')
    
    args = parser.parse_args()
    
    start_time = datetime.now()
    
    # Xử lý các file trùng lặp
    process_duplicates(
        args.input_dir, 
        args.output, 
        hash_method=args.method, 
        action=args.action, 
        verbose=not args.quiet
    )
    
    end_time = datetime.now()
    elapsed_time = end_time - start_time
    
    if not args.quiet:
        print(f"\nThời gian thực hiện: {elapsed_time}")

if __name__ == "__main__":
    main()
