import os
import sys
import pydicom
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from collections import defaultdict
from datetime import datetime
import glob
import traceback
from tqdm import tqdm
import seaborn as sns
from pathlib import Path

class DicomAnalyzer:
    """Phân tích và so sánh file CT và CBCT"""
    
    def __init__(self, root_dir):
        """Khởi tạo với thư mục gốc"""
        self.root_dir = root_dir
        # Dictionary chứa kết quả phân tích
        self.results = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
        # DataFrame kết quả sau khi phân tích
        self.summary_df = None
    
    def scan_directory(self):
        """Quét thư mục tìm tất cả file DICOM"""
        print(f"Đang quét thư mục: {self.root_dir}")
        
        # Tìm tất cả file .dcm
        dicom_files = []
        for root, dirs, files in os.walk(self.root_dir):
            for file in files:
                if file.endswith('.dcm'):
                    dicom_files.append(os.path.join(root, file))
        
        print(f"Tìm thấy {len(dicom_files)} file DICOM")
        return dicom_files
    
    def analyze_dicom_files(self):
        """Phân tích thông tin từ các file DICOM"""
        dicom_files = self.scan_directory()
        
        if not dicom_files:
            print("Không tìm thấy file DICOM nào!")
            return
            
        # Sử dụng tqdm để hiển thị thanh tiến trình
        for file_path in tqdm(dicom_files, desc="Phân tích file DICOM"):
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
                
                # Lưu thông tin vào kết quả
                self.results[patient_id][study_date][modality].append({
                    'file_path': file_path,
                    'file_name': filename,
                    'file_size': file_size,
                    'resolution': resolution,
                    'rows': rows,
                    'cols': cols,
                    'pixel_data_exists': hasattr(dcm, 'PixelData')
                })
                
            except Exception as e:
                print(f"\nLỗi khi xử lý file {file_path}: {str(e)}")
                traceback.print_exc()
    
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
    
    def validate_cross_relationships(self):
        """Kiểm tra chéo mối quan hệ giữa CT và CBCT"""
        if self.summary_df is None:
            self.generate_summary()
        
        if len(self.summary_df) == 0:
            print("Không có đủ dữ liệu để kiểm tra chéo!")
            return
        
        print("\n=== KIỂM TRA CHÉO CT & CBCT ===")
        
        # 1. Kiểm tra dung lượng file
        size_check = self.summary_df[self.summary_df['SizeRatio'] != 'N/A']
        if not size_check.empty:
            avg_size_ratio = size_check['SizeRatio'].astype(float).mean()
            print(f"\nTỷ lệ dung lượng trung bình (CBCT/CT): {avg_size_ratio:.2f}")
            print(f"Kết luận: {'CBCT lớn hơn CT' if avg_size_ratio > 1 else 'CT lớn hơn CBCT'}")
            
            # Kiểm tra % trường hợp CBCT lớn hơn
            larger_count = sum(size_check['SizeRatio'].astype(float) > 1)
            percent_larger = larger_count / len(size_check) * 100
            print(f"CBCT lớn hơn CT trong {percent_larger:.1f}% trường hợp")
        
        # 2. Kiểm tra độ phân giải
        resolution_stats = {}
        for idx, row in self.summary_df.iterrows():
            if row['CT_Resolution'] != 'N/A' and row['CBCT_Resolution'] != 'N/A':
                ct_res = row['CT_Resolution'].split('x')
                cbct_res = row['CBCT_Resolution'].split('x')
                
                try:
                    ct_pixels = int(ct_res[0]) * int(ct_res[1])
                    cbct_pixels = int(cbct_res[0]) * int(cbct_res[1])
                    
                    if ct_res not in resolution_stats:
                        resolution_stats[row['CT_Resolution']] = 0
                    resolution_stats[row['CT_Resolution']] += 1
                    
                    if cbct_res not in resolution_stats:
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
        
        print("\n=== THỐNG KÊ ĐỘ PHÂN GIẢI ===")
        for res, count in resolution_stats.items():
            if res not in ['ratio_sum', 'ratio_count']:
                print(f"{res}: {count} lần")
        
        if 'ratio_sum' in resolution_stats and resolution_stats['ratio_count'] > 0:
            avg_res_ratio = resolution_stats['ratio_sum'] / resolution_stats['ratio_count']
            print(f"\nTỷ lệ pixel trung bình (CBCT/CT): {avg_res_ratio:.2f}")
            print(f"Kết luận: {'CBCT có độ phân giải cao hơn' if avg_res_ratio > 1 else 'CT có độ phân giải cao hơn'}")
        
        # 3. Kiểm tra số lượng ảnh
        count_check = self.summary_df[self.summary_df['CountRatio'] != 'N/A']
        if not count_check.empty:
            avg_count_ratio = count_check['CountRatio'].astype(float).mean()
            print(f"\nTỷ lệ số lượng ảnh trung bình (CT/CBCT): {avg_count_ratio:.2f}")
            print(f"Kết luận: {'CT nhiều ảnh hơn CBCT' if avg_count_ratio > 1 else 'CBCT nhiều ảnh hơn CT'}")
            
            # Kiểm tra % trường hợp CT nhiều ảnh hơn
            more_ct = sum(count_check['CountRatio'].astype(float) > 1)
            percent_more_ct = more_ct / len(count_check) * 100
            print(f"CT nhiều ảnh hơn CBCT trong {percent_more_ct:.1f}% trường hợp")
    
    def create_visualizations(self):
        """Tạo các biểu đồ trực quan so sánh CT và CBCT"""
        if self.summary_df is None:
            self.generate_summary()
        
        if len(self.summary_df) == 0:
            print("Không có đủ dữ liệu để tạo biểu đồ!")
            return
        
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
            plt.savefig(os.path.join(self.root_dir, 'ct_cbct_count_comparison.png'), dpi=300, bbox_inches='tight')
        
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
            plt.savefig(os.path.join(self.root_dir, 'ct_cbct_size_comparison.png'), dpi=300, bbox_inches='tight')
            
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
                plt.savefig(os.path.join(self.root_dir, 'ct_cbct_ratio_heatmap.png'), dpi=300, bbox_inches='tight')
        
        print(f"\nĐã tạo các biểu đồ và lưu vào thư mục: {self.root_dir}")
    
    def export_results(self):
        """Xuất kết quả ra file Excel và CSV"""
        if self.summary_df is None:
            self.generate_summary()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Xuất ra Excel
        excel_path = os.path.join(self.root_dir, f"ct_cbct_analysis_{timestamp}.xlsx")
        self.summary_df.to_excel(excel_path, index=False)
        
        # Xuất ra CSV
        csv_path = os.path.join(self.root_dir, f"ct_cbct_analysis_{timestamp}.csv")
        self.summary_df.to_csv(csv_path, index=False)
        
        print(f"\nĐã xuất kết quả phân tích ra file:")
        print(f"- Excel: {excel_path}")
        print(f"- CSV: {csv_path}")
        
        return excel_path, csv_path
    
    def run_full_analysis(self):
        """Chạy toàn bộ quá trình phân tích"""
        print("Bắt đầu phân tích CT và CBCT...")
        
        # Quét và phân tích file DICOM
        self.analyze_dicom_files()
        
        # Tạo báo cáo tổng hợp
        summary = self.generate_summary()
        print("\n=== BÁO CÁO TỔNG HỢP ===")
        print(summary)
        
        # Kiểm tra chéo mối quan hệ
        self.validate_cross_relationships()
        
        # Tạo biểu đồ
        self.create_visualizations()
        
        # Xuất kết quả
        self.export_results()
        
        print("\nĐã hoàn thành phân tích!")


def main():
    """Hàm chính"""
    # Xử lý tham số dòng lệnh
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        # Nếu không có tham số, yêu cầu người dùng nhập đường dẫn
        root_dir = input("Nhập đường dẫn đến thư mục chứa dữ liệu DICOM: ")
    
    # Kiểm tra thư mục có tồn tại không
    if not os.path.exists(root_dir) or not os.path.isdir(root_dir):
        print(f"Thư mục không tồn tại: {root_dir}")
        return
    
    # Tạo và chạy bộ phân tích
    analyzer = DicomAnalyzer(root_dir)
    analyzer.run_full_analysis()

if __name__ == "__main__":
    main()