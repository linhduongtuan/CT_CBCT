#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Phân tích và so sánh file CT và CBCT - Đã thêm phát hiện outliers
"""

import os
import sys
import argparse
import pydicom
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from datetime import datetime
import traceback
from tqdm import tqdm
import seaborn as sns
from pathlib import Path
import warnings
from scipy import stats

class DicomAnalyzer:
    """Phân tích và so sánh file CT và CBCT với khả năng phát hiện outliers"""
    
    def __init__(self, root_dir, output_dir=None, quiet=False):
        """
        Khởi tạo với thư mục gốc và tùy chọn
        
        Parameters:
        root_dir (str): Thư mục chứa dữ liệu DICOM
        output_dir (str, optional): Thư mục lưu kết quả, mặc định là root_dir
        quiet (bool): Tắt thông báo tiến trình nếu True
        """
        self.root_dir = root_dir
        self.output_dir = output_dir if output_dir else root_dir
        self.quiet = quiet
        # Dictionary chứa kết quả phân tích
        self.results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # DataFrame kết quả sau khi phân tích
        self.summary_df = None
        # DataFrame chi tiết tất cả các file
        self.all_files_df = None
        # Outliers đã phát hiện
        self.outliers = {
            'file_size': defaultdict(list),
            'resolution': defaultdict(list)
        }
        # Giá trị tham chiếu mong đợi cho CT và CBCT
        self.reference_values = {
            'CT': {
                'resolution': {
                    'expected': '512x512',
                    'range': ['256x256', '1024x1024']
                },
                'file_size': {
                    'expected': 0.5,  # MB
                    'range': [0.1, 2.0]  # MB
                }
            },
            'RTIMAGE': {  # CBCT lưu dưới dạng RTIMAGE
                'resolution': {
                    'expected': '1280x1280',
                    'range': ['512x512', '2048x2048']
                },
                'file_size': {
                    'expected': 3.0,  # MB
                    'range': [1.0, 10.0]  # MB
                }
            }
        }
    
    def log(self, message):
        """In thông báo nếu không ở chế độ quiet"""
        if not self.quiet:
            print(message)
    
    def scan_directory(self):
        """Quét thư mục tìm tất cả file DICOM"""
        self.log(f"Đang quét thư mục: {self.root_dir}")
        
        # Tìm tất cả file .dcm
        dicom_files = []
        for root, dirs, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith('.dcm'):
                    dicom_files.append(os.path.join(root, file))
        
        self.log(f"Tìm thấy {len(dicom_files)} file DICOM")
        return dicom_files
    
    def analyze_dicom_files(self):
        """Phân tích thông tin từ các file DICOM"""
        dicom_files = self.scan_directory()
        
        if not dicom_files:
            self.log("Không tìm thấy file DICOM nào!")
            return
        
        # Thu thập dữ liệu chi tiết về từng file
        all_files_data = []
            
        # Sử dụng tqdm để hiển thị thanh tiến trình
        for file_path in tqdm(dicom_files, desc="Phân tích file DICOM", disable=self.quiet):
            try:
                # Đọc metadata (không đọc pixel data)
                dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                
                # Lấy thông tin cơ bản
                patient_id = getattr(dcm, 'PatientID', 'Unknown')
                
                # Xác định loại ảnh (CT/CBCT)
                modality = getattr(dcm, 'Modality', 'Unknown')
                filename = os.path.basename(file_path)
                
                # Xác định loại ảnh dựa trên tên file nếu modality không có
                if modality == 'Unknown' or modality not in ['CT', 'RTIMAGE']:
                    if filename.startswith('CT.'):
                        modality = 'CT'
                    elif filename.startswith('RI.'):
                        modality = 'RTIMAGE'  # CBCT thường được lưu dưới dạng RTIMAGE
                
                # Lấy thông tin thời gian chụp
                study_date = None
                if hasattr(dcm, 'StudyDate') and dcm.StudyDate:
                    # Format DICOM date thành YYYY-MM-DD
                    date_str = dcm.StudyDate
                    if len(date_str) == 8:
                        study_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                
                # Nếu không có StudyDate, thử đọc AcquisitionDate
                if not study_date and hasattr(dcm, 'AcquisitionDate') and dcm.AcquisitionDate:
                    date_str = dcm.AcquisitionDate
                    if len(date_str) == 8:
                        study_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                
                # Nếu vẫn không có, thử lấy từ đường dẫn
                if not study_date:
                    # Tìm các thành phần giống định dạng ngày trong đường dẫn
                    path_parts = file_path.split(os.sep)
                    for part in path_parts:
                        if part.count('-') == 2:  # Có thể là định dạng YYYY-MM-DD
                            try:
                                datetime.strptime(part, '%Y-%m-%d')
                                study_date = part
                                break
                            except ValueError:
                                pass
                
                # Nếu vẫn không tìm được ngày, đánh dấu là "Unknown"
                if not study_date:
                    study_date = "Unknown"
                
                # Lấy kích thước file (MB)
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                
                # Lấy độ phân giải
                rows = getattr(dcm, 'Rows', 0)
                cols = getattr(dcm, 'Columns', 0)
                resolution = f"{rows}x{cols}"
                pixel_count = rows * cols if rows > 0 and cols > 0 else 0
                
                # Thu thập thêm thông tin chi tiết
                file_info = {
                    'file_path': file_path,
                    'file_name': filename,
                    'patient_id': patient_id,
                    'study_date': study_date,
                    'modality': modality,
                    'file_size': file_size,
                    'resolution': resolution,
                    'rows': rows,
                    'cols': cols,
                    'pixel_count': pixel_count,
                    'manufacturer': getattr(dcm, 'Manufacturer', 'Unknown'),
                    'manufacturer_model': getattr(dcm, 'ManufacturerModelName', 'Unknown'),
                    'pixel_data_exists': hasattr(dcm, 'PixelData'),
                    'bits_allocated': getattr(dcm, 'BitsAllocated', 0) if hasattr(dcm, 'BitsAllocated') else 0,
                    'bits_stored': getattr(dcm, 'BitsStored', 0) if hasattr(dcm, 'BitsStored') else 0
                }
                
                # Thêm vào kết quả theo cấu trúc phân cấp
                self.results[patient_id][study_date][modality].append(file_info)
                
                # Thêm vào danh sách chi tiết
                all_files_data.append(file_info)
                
            except Exception as e:
                if not self.quiet:
                    sys.stderr.write(f"\nLỗi khi xử lý file {file_path}: {str(e)}\n")
        
        # Tạo DataFrame chi tiết của tất cả các file
        if all_files_data:
            self.all_files_df = pd.DataFrame(all_files_data)
    
    def generate_summary(self):
        """Tạo báo cáo tổng hợp từ kết quả phân tích"""
        summary_data = []
        
        for patient_id, patient_data in self.results.items():
            for study_date, date_data in patient_data.items():
                # Thông tin CT
                ct_files = date_data.get('CT', [])
                ct_count = len(ct_files)
                ct_avg_size = np.mean([f['file_size'] for f in ct_files]) if ct_files else 0
                ct_resolution = ct_files[0]['resolution'] if ct_files else 'N/A'
                
                # Thông tin CBCT/RTIMAGE
                cbct_files = date_data.get('RTIMAGE', [])
                cbct_count = len(cbct_files)
                cbct_avg_size = np.mean([f['file_size'] for f in cbct_files]) if cbct_files else 0
                cbct_resolution = cbct_files[0]['resolution'] if cbct_files else 'N/A'
                
                # Thêm vào dữ liệu tổng hợp
                summary_data.append({
                    'PatientID': patient_id,
                    'StudyDate': study_date,
                    'CT_Count': ct_count,
                    'CT_AvgSize_MB': round(ct_avg_size, 2),
                    'CT_Resolution': ct_resolution,
                    'CBCT_Count': cbct_count,
                    'CBCT_AvgSize_MB': round(cbct_avg_size, 2),
                    'CBCT_Resolution': cbct_resolution,
                    'SizeRatio': round(cbct_avg_size / ct_avg_size, 2) if ct_avg_size > 0 and cbct_avg_size > 0 else 'N/A',
                    'CountRatio': round(ct_count / cbct_count, 2) if cbct_count > 0 and ct_count > 0 else 'N/A'
                })
        
        # Tạo DataFrame từ dữ liệu
        self.summary_df = pd.DataFrame(summary_data)
        return self.summary_df
    
    def detect_file_size_outliers(self, method="iqr", threshold=1.5):
        """
        Phát hiện outlier về kích thước file
        
        Parameters:
        method (str): Phương pháp phát hiện, 'iqr' hoặc 'zscore' hoặc 'reference'
        threshold (float): Ngưỡng cho phương pháp IQR hoặc Z-score
        """
        if self.all_files_df is None or len(self.all_files_df) == 0:
            self.log("Không có dữ liệu để phát hiện outliers")
            return []
        
        outliers = []
        
        # Phân tích theo từng loại modality
        for modality in self.all_files_df['modality'].unique():
            # Lọc dữ liệu theo modality
            mod_data = self.all_files_df[self.all_files_df['modality'] == modality]
            
            if len(mod_data) < 5:  # Cần đủ dữ liệu để phân tích
                continue
                
            file_sizes = mod_data['file_size'].values
            
            # Phương pháp IQR
            if method == "iqr":
                q1 = np.percentile(file_sizes, 25)
                q3 = np.percentile(file_sizes, 75)
                iqr = q3 - q1
                lower_bound = q1 - threshold * iqr
                upper_bound = q3 + threshold * iqr
                
                for idx, row in mod_data.iterrows():
                    if row['file_size'] < lower_bound or row['file_size'] > upper_bound:
                        outliers.append({
                            'file_path': row['file_path'],
                            'file_name': row['file_name'],
                            'patient_id': row['patient_id'],
                            'study_date': row['study_date'],
                            'modality': row['modality'],
                            'file_size': row['file_size'],
                            'mean': np.mean(file_sizes),
                            'std': np.std(file_sizes),
                            'threshold': threshold,
                            'lower_bound': lower_bound,
                            'upper_bound': upper_bound,
                            'issue_type': 'file_size',
                            'issue_desc': f'{"Nhỏ bất thường" if row["file_size"] < lower_bound else "Lớn bất thường"}'
                        })
            
            # Phương pháp Z-score
            elif method == "zscore":
                mean = np.mean(file_sizes)
                std = np.std(file_sizes)
                
                if std == 0:  # Tránh chia cho 0
                    continue
                    
                for idx, row in mod_data.iterrows():
                    z_score = abs((row['file_size'] - mean) / std)
                    if z_score > threshold:
                        outliers.append({
                            'file_path': row['file_path'],
                            'file_name': row['file_name'],
                            'patient_id': row['patient_id'],
                            'study_date': row['study_date'],
                            'modality': row['modality'],
                            'file_size': row['file_size'],
                            'mean': mean,
                            'std': std,
                            'z_score': z_score,
                            'threshold': threshold,
                            'issue_type': 'file_size',
                            'issue_desc': f'Z-score = {z_score:.2f}, vượt ngưỡng {threshold}'
                        })
            
            # Phương pháp so sánh với giá trị tham chiếu
            elif method == "reference":
                if modality in self.reference_values:
                    lower = self.reference_values[modality]['file_size']['range'][0]
                    upper = self.reference_values[modality]['file_size']['range'][1]
                    
                    for idx, row in mod_data.iterrows():
                        if row['file_size'] < lower or row['file_size'] > upper:
                            outliers.append({
                                'file_path': row['file_path'],
                                'file_name': row['file_name'],
                                'patient_id': row['patient_id'],
                                'study_date': row['study_date'],
                                'modality': row['modality'],
                                'file_size': row['file_size'],
                                'expected_min': lower,
                                'expected_max': upper,
                                'issue_type': 'file_size',
                                'issue_desc': f'Kích thước {row["file_size"]:.2f} MB nằm ngoài phạm vi mong đợi [{lower}-{upper}] MB'
                            })
        
        # Lưu kết quả
        self.outliers['file_size'] = outliers
        return outliers
    
    def detect_resolution_outliers(self, method="reference"):
        """
        Phát hiện outlier về độ phân giải
        
        Parameters:
        method (str): Phương pháp phát hiện, chủ yếu là 'reference' cho phân giải
        """
        if self.all_files_df is None or len(self.all_files_df) == 0:
            self.log("Không có dữ liệu để phát hiện outliers")
            return []
        
        outliers = []
        
        # Phân tích theo từng loại modality
        for modality in self.all_files_df['modality'].unique():
            # Lọc dữ liệu theo modality
            mod_data = self.all_files_df[self.all_files_df['modality'] == modality]
            
            if len(mod_data) < 3:  # Cần đủ dữ liệu để phân tích
                continue
                
            # Phương pháp so sánh với giá trị tham chiếu
            if method == "reference" and modality in self.reference_values:
                expected = self.reference_values[modality]['resolution']['expected']
                allowed = self.reference_values[modality]['resolution']['range']
                
                for idx, row in mod_data.iterrows():
                    if row['resolution'] not in allowed and row['resolution'] != expected:
                        outliers.append({
                            'file_path': row['file_path'],
                            'file_name': row['file_name'],
                            'patient_id': row['patient_id'],
                            'study_date': row['study_date'],
                            'modality': row['modality'],
                            'resolution': row['resolution'],
                            'expected': expected,
                            'allowed': allowed,
                            'issue_type': 'resolution',
                            'issue_desc': f'Độ phân giải {row["resolution"]} khác với giá trị mong đợi {expected}'
                        })
            
            # Phương pháp so sánh với độ phân giải phổ biến nhất
            elif method == "mode":
                # Tìm độ phân giải phổ biến nhất
                resolution_counts = mod_data['resolution'].value_counts()
                mode_resolution = resolution_counts.index[0] if not resolution_counts.empty else None
                
                if mode_resolution:
                    for idx, row in mod_data.iterrows():
                        if row['resolution'] != mode_resolution:
                            outliers.append({
                                'file_path': row['file_path'],
                                'file_name': row['file_name'],
                                'patient_id': row['patient_id'],
                                'study_date': row['study_date'],
                                'modality': row['modality'],
                                'resolution': row['resolution'],
                                'mode_resolution': mode_resolution,
                                'issue_type': 'resolution',
                                'issue_desc': f'Độ phân giải {row["resolution"]} khác với giá trị phổ biến {mode_resolution}'
                            })
        
        # Lưu kết quả
        self.outliers['resolution'] = outliers
        return outliers
    
    def analyze_outliers(self):
        """Phân tích tất cả các loại outliers và tạo báo cáo"""
        # Phát hiện outliers
        file_size_outliers_iqr = self.detect_file_size_outliers(method="iqr")
        file_size_outliers_ref = self.detect_file_size_outliers(method="reference")
        resolution_outliers = self.detect_resolution_outliers()
        
        # Tổng hợp kết quả
        total_files = len(self.all_files_df) if self.all_files_df is not None else 0
        
        self.log("\n=== BÁO CÁO OUTLIERS ===")
        self.log(f"Tổng số file: {total_files}")
        self.log(f"Số file có kích thước bất thường (IQR): {len(file_size_outliers_iqr)}")
        self.log(f"Số file có kích thước bất thường (Tham chiếu): {len(file_size_outliers_ref)}")
        self.log(f"Số file có độ phân giải bất thường: {len(resolution_outliers)}")
        
        # Chi tiết về outliers theo loại modality
        if self.all_files_df is not None:
            for modality in self.all_files_df['modality'].unique():
                mod_count = len(self.all_files_df[self.all_files_df['modality'] == modality])
                size_outliers = [o for o in file_size_outliers_iqr if o['modality'] == modality]
                res_outliers = [o for o in resolution_outliers if o['modality'] == modality]
                
                self.log(f"\n{modality} ({mod_count} files):")
                self.log(f"  - Kích thước bất thường: {len(size_outliers)} files ({len(size_outliers)/mod_count*100:.1f}%)")
                self.log(f"  - Độ phân giải bất thường: {len(res_outliers)} files ({len(res_outliers)/mod_count*100:.1f}%)")
                
                # Chi tiết hơn về kích thước file
                if len(size_outliers) > 0:
                    size_df = pd.DataFrame(size_outliers)
                    self.log("\n  Chi tiết kích thước bất thường:")
                    for desc, group in size_df.groupby('issue_desc'):
                        self.log(f"    {desc}: {len(group)} files")
                        for i, row in enumerate(group.iloc[:5].itertuples()):
                            self.log(f"      {i+1}. {os.path.basename(row.file_path)}: {row.file_size:.2f} MB")
                        if len(group) > 5:
                            self.log(f"      ... và {len(group) - 5} file khác")
                
                # Chi tiết về độ phân giải
                if len(res_outliers) > 0:
                    res_df = pd.DataFrame(res_outliers)
                    unique_resolutions = res_df['resolution'].unique()
                    self.log("\n  Chi tiết độ phân giải bất thường:")
                    for res in unique_resolutions:
                        count = len(res_df[res_df['resolution'] == res])
                        self.log(f"    {res}: {count} files")
        
        # Tạo DataFrame outliers để export
        all_outliers = []
        for outlier_type, outliers_list in self.outliers.items():
            for outlier in outliers_list:
                outlier['outlier_type'] = outlier_type
                all_outliers.append(outlier)
        
        return all_outliers
    
    def visualize_outliers(self):
        """Tạo biểu đồ trực quan cho các outliers"""
        if self.all_files_df is None or len(self.all_files_df) == 0:
            self.log("Không có dữ liệu để tạo biểu đồ")
            return
        
        # Đảm bảo thư mục đầu ra tồn tại
        os.makedirs(self.output_dir, exist_ok=True)
        
        # 1. Biểu đồ boxplot kích thước file theo modality
        plt.figure(figsize=(12, 7))
        sns.boxplot(x='modality', y='file_size', data=self.all_files_df)
        plt.title('Phân bố kích thước file theo loại')
        plt.xlabel('Loại ảnh')
        plt.ylabel('Kích thước file (MB)')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'file_size_boxplot.png'), dpi=300, bbox_inches='tight')
        
        # 2. Biểu đồ phân bố kích thước cho từng loại riêng biệt
        for modality in self.all_files_df['modality'].unique():
            mod_data = self.all_files_df[self.all_files_df['modality'] == modality]
            
            if len(mod_data) < 5:
                continue
                
            plt.figure(figsize=(12, 7))
            
            # Histogram và KDE
            sns.histplot(mod_data['file_size'], kde=True, bins=30)
            
            # Vẽ các đường vertical cho outliers
            if modality in self.reference_values:
                lower = self.reference_values[modality]['file_size']['range'][0]
                upper = self.reference_values[modality]['file_size']['range'][1]
                expected = self.reference_values[modality]['file_size']['expected']
                
                plt.axvline(x=lower, color='r', linestyle='--', label=f'Min Expected: {lower} MB')
                plt.axvline(x=upper, color='r', linestyle='--', label=f'Max Expected: {upper} MB')
                plt.axvline(x=expected, color='g', linestyle='-', label=f'Expected: {expected} MB')
            
            plt.title(f'Phân bố kích thước file {modality}')
            plt.xlabel('Kích thước file (MB)')
            plt.ylabel('Số lượng')
            plt.legend()
            plt.grid(True, alpha=0.3)
            plt.tight_layout()
            plt.savefig(os.path.join(self.output_dir, f'file_size_dist_{modality}.png'), dpi=300, bbox_inches='tight')
        
        # 3. Biểu đồ phân bố độ phân giải
        plt.figure(figsize=(14, 7))
        
        # Tạo DataFrame với số lượng của mỗi độ phân giải
        resolution_counts = self.all_files_df.groupby(['modality', 'resolution']).size().reset_index(name='count')
        
        # Vẽ biểu đồ cột
        ax = sns.barplot(x='resolution', y='count', hue='modality', data=resolution_counts)
        
        plt.title('Phân bố độ phân giải theo loại ảnh')
        plt.xlabel('Độ phân giải')
        plt.ylabel('Số lượng file')
        plt.xticks(rotation=45)
        plt.legend(title='Loại ảnh')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, 'resolution_distribution.png'), dpi=300, bbox_inches='tight')
        
        # 4. Heatmap cho outliers theo bệnh nhân và ngày
        try:
            # Tạo DataFrame với số lượng outliers theo bệnh nhân, ngày chụp
            outlier_counts = pd.DataFrame()
            
            if hasattr(self, 'outliers') and 'file_size' in self.outliers and len(self.outliers['file_size']) > 0:
                size_outliers_df = pd.DataFrame(self.outliers['file_size'])
                if len(size_outliers_df) > 0:
                    size_counts = size_outliers_df.groupby(['patient_id', 'study_date', 'modality']).size().reset_index(name='size_outliers')
                    
                    if outlier_counts.empty:
                        outlier_counts = size_counts
                    else:
                        outlier_counts = pd.merge(outlier_counts, size_counts, 
                                                on=['patient_id', 'study_date', 'modality'], 
                                                how='outer').fillna(0)
            
            if hasattr(self, 'outliers') and 'resolution' in self.outliers and len(self.outliers['resolution']) > 0:
                res_outliers_df = pd.DataFrame(self.outliers['resolution'])
                if len(res_outliers_df) > 0:
                    res_counts = res_outliers_df.groupby(['patient_id', 'study_date', 'modality']).size().reset_index(name='resolution_outliers')
                    
                    if outlier_counts.empty:
                        outlier_counts = res_counts
                    else:
                        outlier_counts = pd.merge(outlier_counts, res_counts, 
                                                on=['patient_id', 'study_date', 'modality'], 
                                                how='outer').fillna(0)
            
            # Tạo heatmap nếu có đủ dữ liệu
            if not outlier_counts.empty and len(outlier_counts) > 1:
                plt.figure(figsize=(14, 10))
                
                # Tạo nhãn cho từng hàng
                outlier_counts['label'] = outlier_counts['patient_id'] + ' (' + outlier_counts['study_date'] + ') ' + outlier_counts['modality']
                
                # Cột dữ liệu cho heatmap
                heatmap_columns = [col for col in outlier_counts.columns if col.endswith('_outliers')]
                
                if heatmap_columns:
                    # Pivot table để tạo heatmap
                    heatmap_data = outlier_counts.pivot(index='label', columns=None, values=heatmap_columns)
                    
                    # Vẽ heatmap
                    sns.heatmap(heatmap_data, annot=True, cmap="YlOrRd", fmt='g')
                    plt.title('Phân bố outliers theo bệnh nhân, ngày và loại ảnh')
                    plt.tight_layout()
                    plt.savefig(os.path.join(self.output_dir, 'outliers_heatmap.png'), dpi=300, bbox_inches='tight')
        except Exception as e:
            self.log(f"Lỗi khi tạo heatmap outliers: {str(e)}")
            traceback.print_exc()
        
        self.log(f"Đã tạo các biểu đồ outliers và lưu vào thư mục: {self.output_dir}")
    
    def export_outliers_report(self):
        """Xuất báo cáo outliers ra file"""
        if not hasattr(self, 'outliers') or not self.outliers:
            self.log("Không có dữ liệu outliers để xuất")
            return None
        
        # Tạo DataFrame chứa tất cả outliers
        all_outliers = []
        for outlier_type, outliers_list in self.outliers.items():
            for outlier in outliers_list:
                outlier_info = {
                    'outlier_type': outlier_type,
                    'file_name': outlier.get('file_name', ''),
                    'file_path': outlier.get('file_path', ''),
                    'patient_id': outlier.get('patient_id', ''),
                    'study_date': outlier.get('study_date', ''),
                    'modality': outlier.get('modality', ''),
                    'issue_desc': outlier.get('issue_desc', '')
                }
                
                # Thêm thông tin chi tiết tùy loại
                if outlier_type == 'file_size':
                    outlier_info.update({
                        'value': outlier.get('file_size', 0),
                        'unit': 'MB'
                    })
                elif outlier_type == 'resolution':
                    outlier_info.update({
                        'value': outlier.get('resolution', ''),
                        'expected': outlier.get('expected', ''),
                        'unit': 'pixels'
                    })
                
                all_outliers.append(outlier_info)
        
        if not all_outliers:
            return None
            
        # Tạo DataFrame
        outliers_df = pd.DataFrame(all_outliers)
        
        # Đảm bảo thư mục đầu ra tồn tại
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Xuất ra Excel
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        excel_path = os.path.join(self.output_dir, f"dicom_outliers_{timestamp}.xlsx")
        outliers_df.to_excel(excel_path, index=False)
        
        self.log(f"\nĐã xuất báo cáo outliers ra file: {excel_path}")
        return excel_path
    
    def validate_cross_relationships(self):
        """Kiểm tra chéo mối quan hệ giữa CT và CBCT"""
        if self.summary_df is None:
            self.generate_summary()
        
        if len(self.summary_df) == 0:
            self.log("Không có đủ dữ liệu để kiểm tra chéo!")
            return
        
        self.log("\n=== KIỂM TRA CHÉO CT & CBCT ===")
        
        # 1. Kiểm tra dung lượng file
        size_check = self.summary_df[self.summary_df['SizeRatio'] != 'N/A']
        if not size_check.empty:
            avg_size_ratio = size_check['SizeRatio'].astype(float).mean()
            self.log(f"\nTỷ lệ dung lượng trung bình (CBCT/CT): {avg_size_ratio:.2f}")
            self.log(f"Kết luận: {'CBCT lớn hơn CT' if avg_size_ratio > 1 else 'CT lớn hơn CBCT'}")
            
            # Kiểm tra % trường hợp CBCT lớn hơn
            larger_count = sum(size_check['SizeRatio'].astype(float) > 1)
            percent_larger = larger_count / len(size_check) * 100
            self.log(f"CBCT lớn hơn CT trong {percent_larger:.1f}% trường hợp")
            
            # Phát hiện outliers trong tỷ lệ kích thước
            size_ratios = size_check['SizeRatio'].astype(float).values
            q1 = np.percentile(size_ratios, 25)
            q3 = np.percentile(size_ratios, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            outlier_ratios = size_check[(size_check['SizeRatio'].astype(float) < lower_bound) | 
                                        (size_check['SizeRatio'].astype(float) > upper_bound)]
            
            if not outlier_ratios.empty:
                self.log("\nPhát hiện tỷ lệ kích thước bất thường:")
                for _, row in outlier_ratios.iterrows():
                    self.log(f"  - Bệnh nhân {row['PatientID']}, ngày {row['StudyDate']}: " + 
                           f"Tỷ lệ = {float(row['SizeRatio']):.2f} (CT: {row['CT_AvgSize_MB']} MB, CBCT: {row['CBCT_AvgSize_MB']} MB)")
        
        # 2. Kiểm tra độ phân giải
        resolution_stats = {}
        for idx, row in self.summary_df.iterrows():
            if row['CT_Resolution'] != 'N/A' and row['CBCT_Resolution'] != 'N/A':
                ct_res = row['CT_Resolution'].split('x')
                cbct_res = row['CBCT_Resolution'].split('x')
                
                try:
                    ct_pixels = int(ct_res[0]) * int(ct_res[1])
                    cbct_pixels = int(cbct_res[0]) * int(cbct_res[1])
                    
                    if row['CT_Resolution'] not in resolution_stats:
                        resolution_stats[row['CT_Resolution']] = 0
                    resolution_stats[row['CT_Resolution']] += 1
                    
                    if row['CBCT_Resolution'] not in resolution_stats:
                        resolution_stats[row['CBCT_Resolution']] = 0
                    resolution_stats[row['CBCT_Resolution']] += 1
                    
                    # So sánh số lượng pixel
                    ratio = cbct_pixels / ct_pixels if ct_pixels > 0 else float('inf')
                    resolution_stats.setdefault('ratio_sum', 0)
                    resolution_stats['ratio_sum'] += ratio
                    resolution_stats.setdefault('ratio_count', 0)
                    resolution_stats['ratio_count'] += 1
                except:
                    pass
        
        self.log("\n=== THỐNG KÊ ĐỘ PHÂN GIẢI ===")
        for res, count in resolution_stats.items():
            if res not in ['ratio_sum', 'ratio_count']:
                self.log(f"{res}: {count} lần")
        
        if 'ratio_sum' in resolution_stats and resolution_stats['ratio_count'] > 0:
            avg_res_ratio = resolution_stats['ratio_sum'] / resolution_stats['ratio_count']
            self.log(f"\nTỷ lệ pixel trung bình (CBCT/CT): {avg_res_ratio:.2f}")
            self.log(f"Kết luận: {'CBCT có độ phân giải cao hơn' if avg_res_ratio > 1 else 'CT có độ phân giải cao hơn'}")
        
        # 3. Kiểm tra số lượng ảnh
        count_check = self.summary_df[self.summary_df['CountRatio'] != 'N/A']
        if not count_check.empty:
            avg_count_ratio = count_check['CountRatio'].astype(float).mean()
            self.log(f"\nTỷ lệ số lượng ảnh trung bình (CT/CBCT): {avg_count_ratio:.2f}")
            self.log(f"Kết luận: {'CT nhiều ảnh hơn CBCT' if avg_count_ratio > 1 else 'CBCT nhiều ảnh hơn CT'}")
            
            # Kiểm tra % trường hợp CT nhiều ảnh hơn
            more_ct = sum(count_check['CountRatio'].astype(float) > 1)
            percent_more_ct = more_ct / len(count_check) * 100
            self.log(f"CT nhiều ảnh hơn CBCT trong {percent_more_ct:.1f}% trường hợp")
            
            # Phát hiện outliers trong tỷ lệ số lượng ảnh
            count_ratios = count_check['CountRatio'].astype(float).values
            q1 = np.percentile(count_ratios, 25)
            q3 = np.percentile(count_ratios, 75)
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            
            outlier_counts = count_check[(count_check['CountRatio'].astype(float) < lower_bound) | 
                                       (count_check['CountRatio'].astype(float) > upper_bound)]
            
            if not outlier_counts.empty:
                self.log("\nPhát hiện tỷ lệ số lượng ảnh bất thường:")
                for _, row in outlier_counts.iterrows():
                    self.log(f"  - Bệnh nhân {row['PatientID']}, ngày {row['StudyDate']}: " + 
                          f"Tỷ lệ = {float(row['CountRatio']):.2f} (CT: {row['CT_Count']}, CBCT: {row['CBCT_Count']})")
    
    def create_visualizations(self):
        """Tạo các biểu đồ trực quan so sánh CT và CBCT"""
        if self.summary_df is None:
            self.generate_summary()
        
        if len(self.summary_df) == 0:
            self.log("Không có đủ dữ liệu để tạo biểu đồ!")
            return
        
        # Đảm bảo thư mục đầu ra tồn tại
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Chuyển đổi cột SizeRatio và CountRatio sang số nếu là chuỗi 'N/A'
        for col in ['SizeRatio', 'CountRatio']:
            self.summary_df[col] = pd.to_numeric(self.summary_df[col], errors='coerce')
        
        # 1. Biểu đồ so sánh số lượng CT và CBCT theo ngày
        plt.figure(figsize=(12, 7))
        
        # Lọc dữ liệu có cả CT và CBCT
        plot_data = self.summary_df[(self.summary_df['CT_Count'] > 0) & (self.summary_df['CBCT_Count'] > 0)]
        
        if len(plot_data) > 0:
            # Tạo index cho trục x
            plot_data = plot_data.copy()
            plot_data['Label'] = plot_data['PatientID'] + ' (' + plot_data['StudyDate'] + ')'
            
            # Tạo biểu đồ cột
            barwidth = 0.35
            r1 = np.arange(len(plot_data))
            r2 = [x + barwidth for x in r1]
            
            plt.bar(r1, plot_data['CT_Count'], width=barwidth, label='CT Images', color='skyblue')
            plt.bar(r2, plot_data['CBCT_Count'], width=barwidth, label='CBCT Images', color='salmon')
            
            plt.xlabel('Bệnh nhân (Ngày)')
            plt.ylabel('Số lượng ảnh')
            plt.title('So sánh số lượng ảnh CT và CBCT theo bệnh nhân và ngày')
            plt.xticks([r + barwidth/2 for r in range(len(plot_data))], plot_data['Label'], rotation=45, ha='right')
            plt.legend()
            plt.tight_layout()
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Lưu biểu đồ
            plt.savefig(os.path.join(self.output_dir, 'ct_cbct_count_comparison.png'), dpi=300, bbox_inches='tight')
        
        # 2. Biểu đồ so sánh kích thước file trung bình
        plt.figure(figsize=(12, 7))
        
        if len(plot_data) > 0:
            barwidth = 0.35
            r1 = np.arange(len(plot_data))
            r2 = [x + barwidth for x in r1]
            
            plt.bar(r1, plot_data['CT_AvgSize_MB'], width=barwidth, label='CT Avg Size (MB)', color='lightblue')
            plt.bar(r2, plot_data['CBCT_AvgSize_MB'], width=barwidth, label='CBCT Avg Size (MB)', color='lightcoral')
            
            plt.xlabel('Bệnh nhân (Ngày)')
            plt.ylabel('Dung lượng trung bình (MB)')
            plt.title('So sánh dung lượng trung bình file CT và CBCT')
            plt.xticks([r + barwidth/2 for r in range(len(plot_data))], plot_data['Label'], rotation=45, ha='right')
            plt.legend()
            plt.tight_layout()
            plt.grid(axis='y', linestyle='--', alpha=0.7)
            
            # Lưu biểu đồ
            plt.savefig(os.path.join(self.output_dir, 'ct_cbct_size_comparison.png'), dpi=300, bbox_inches='tight')
            
        # 3. Biểu đồ heatmap về tỷ lệ
        if len(self.summary_df) > 1:  # Cần ít nhất 2 hàng để vẽ heatmap
            plt.figure(figsize=(10, 8))
            
            # Chuẩn bị dữ liệu cho heatmap
            heatmap_data = self.summary_df[['PatientID', 'StudyDate', 'SizeRatio', 'CountRatio']].copy()
            heatmap_data = heatmap_data.dropna()
            
            if len(heatmap_data) > 0:
                # Tạo pivot table
                heatmap_data['Label'] = heatmap_data['PatientID'] + ' (' + heatmap_data['StudyDate'] + ')'
                pivot_data = pd.DataFrame({
                    'Label': heatmap_data['Label'],
                    'Size Ratio (CBCT/CT)': heatmap_data['SizeRatio'],
                    'Count Ratio (CT/CBCT)': heatmap_data['CountRatio']
                })
                pivot_data = pivot_data.set_index('Label').T
                
                # Vẽ heatmap
                sns.heatmap(pivot_data, annot=True, cmap="YlGnBu", fmt='.2f', linewidths=.5)
                plt.title('Tỷ lệ kích thước và số lượng ảnh giữa CT và CBCT')
                plt.tight_layout()
                
                # Lưu biểu đồ
                plt.savefig(os.path.join(self.output_dir, 'ct_cbct_ratio_heatmap.png'), dpi=300, bbox_inches='tight')
        
        self.log(f"\nĐã tạo các biểu đồ và lưu vào thư mục: {self.output_dir}")
    
    def export_results(self):
        """Xuất kết quả ra file Excel và CSV"""
        if self.summary_df is None:
            self.generate_summary()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Đảm bảo thư mục đầu ra tồn tại
        os.makedirs(self.output_dir, exist_ok=True)
        
        # Xuất ra Excel
        excel_path = os.path.join(self.output_dir, f"ct_cbct_analysis_{timestamp}.xlsx")
        self.summary_df.to_excel(excel_path, index=False)
        
        # Xuất ra CSV
        csv_path = os.path.join(self.output_dir, f"ct_cbct_analysis_{timestamp}.csv")
        self.summary_df.to_csv(csv_path, index=False)
        
        # Xuất chi tiết tất cả các file
        if self.all_files_df is not None:
            detail_path = os.path.join(self.output_dir, f"ct_cbct_details_{timestamp}.xlsx")
            with pd.ExcelWriter(detail_path) as writer:
                self.all_files_df.to_excel(writer, sheet_name='Files', index=False)
                
                # Thêm sheet outliers nếu có
                all_outliers = []
                for outlier_type, outliers_list in self.outliers.items():
                    for outlier in outliers_list:
                        outlier['outlier_type'] = outlier_type
                        all_outliers.append(outlier)
                
                if all_outliers:
                    outliers_df = pd.DataFrame(all_outliers)
                    outliers_df.to_excel(writer, sheet_name='Outliers', index=False)
                    
                # Thêm sheet tóm tắt
                self.summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            self.log(f"- Chi tiết: {detail_path}")
        
        self.log(f"\nĐã xuất kết quả phân tích ra file:")
        self.log(f"- Excel: {excel_path}")
        self.log(f"- CSV: {csv_path}")
        
        return excel_path, csv_path
    
    def run_full_analysis(self):
        """Chạy toàn bộ quá trình phân tích"""
        self.log("Bắt đầu phân tích CT và CBCT...")
        
        # Quét và phân tích file DICOM
        self.analyze_dicom_files()
        
        # Tạo báo cáo tổng hợp
        summary = self.generate_summary()
        self.log("\n=== BÁO CÁO TỔNG HỢP ===")
        self.log(summary)
        
        # Kiểm tra chéo mối quan hệ
        self.validate_cross_relationships()
        
        # Tìm và phân tích outliers
        self.log("\nĐang tìm kiếm các trường hợp ngoại lệ (outliers)...")
        self.analyze_outliers()
        
        # Tạo biểu đồ
        self.create_visualizations()
        
        # Tạo biểu đồ cho outliers
        self.visualize_outliers()
        
        # Xuất báo cáo outliers
        self.export_outliers_report()
        
        # Xuất kết quả tổng thể
        self.export_results()
        
        self.log("\nĐã hoàn thành phân tích!")


def main():
    """Hàm chính"""
    # Tắt cảnh báo từ matplotlib
    warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")
    
    parser = argparse.ArgumentParser(
        description='Phân tích và so sánh ảnh CT và CBCT trong thư mục DICOM, bao gồm phát hiện outliers',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument('input_dir', nargs='?', help='Thư mục chứa dữ liệu DICOM')
    parser.add_argument('-o', '--output-dir', help='Thư mục lưu kết quả (mặc định là thư mục đầu vào)')
    parser.add_argument('-q', '--quiet', action='store_true', help='Chế độ yên lặng, không hiển thị thông báo tiến trình')
    parser.add_argument('--active', action='store_true', help='Sử dụng môi trường ảo hiện tại (cho uv run)')
    
    args = parser.parse_args()
    
    # Nếu không có đối số đường dẫn, yêu cầu người dùng nhập
    input_dir = args.input_dir
    if not input_dir:
        input_dir = input("Nhập đường dẫn đến thư mục chứa dữ liệu DICOM: ")
    
    # Kiểm tra thư mục có tồn tại không
    if not os.path.exists(input_dir) or not os.path.isdir(input_dir):
        print(f"Thư mục không tồn tại: {input_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Tạo và chạy bộ phân tích
    analyzer = DicomAnalyzer(
        root_dir=input_dir,
        output_dir=args.output_dir, 
        quiet=args.quiet
    )
    analyzer.run_full_analysis()

if __name__ == "__main__":
    main()
