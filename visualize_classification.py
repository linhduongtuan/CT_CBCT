import os
import sys
import numpy as np
import pydicom
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, RadioButtons
from datetime import datetime

def load_dicom_paths_from_txt(txt_file_path):
    """Đọc danh sách đường dẫn đến các file DICOM từ file txt"""
    with open(txt_file_path, 'r') as f:
        paths = [line.strip() for line in f.readlines()]
    return paths

def load_dicom_series(dicom_paths):
    """Tải một chuỗi ảnh DICOM và sắp xếp theo vị trí"""
    slices = []
    for path in dicom_paths:
        try:
            dcm = pydicom.dcmread(path, force=True)
            slices.append(dcm)
        except Exception as e:
            print(f"Không thể đọc file {path}: {e}")
    
    # Sắp xếp theo vị trí lát cắt (nếu có)
    try:
        slices = sorted(slices, key=lambda x: float(x.ImagePositionPatient[2]))
    except:
        try:
            slices = sorted(slices, key=lambda x: float(x.InstanceNumber))
        except:
            print("Không thể sắp xếp lát cắt theo vị trí, giữ nguyên thứ tự")
    
    return slices

def extract_dicom_info(dcm):
    """Trích xuất thông tin quan trọng từ file DICOM"""
    info = {}
    
    # Thông tin cơ bản
    try: info['PatientID'] = dcm.PatientID
    except: info['PatientID'] = 'N/A'
    
    try: info['PatientName'] = str(dcm.PatientName)
    except: info['PatientName'] = 'N/A'
    
    try: info['Modality'] = dcm.Modality
    except: info['Modality'] = 'N/A'
    
    # Thông tin thời gian
    try: 
        study_date = dcm.StudyDate
        info['StudyDate'] = f"{study_date[:4]}-{study_date[4:6]}-{study_date[6:]}"
    except: info['StudyDate'] = 'N/A'
    
    try: 
        acq_date = dcm.AcquisitionDate
        info['AcquisitionDate'] = f"{acq_date[:4]}-{acq_date[4:6]}-{acq_date[6:]}"
    except: info['AcquisitionDate'] = 'N/A'
    
    # Thông tin mô tả
    try: info['StudyDescription'] = dcm.StudyDescription
    except: info['StudyDescription'] = 'N/A'
    
    try: info['SeriesDescription'] = dcm.SeriesDescription
    except: info['SeriesDescription'] = 'N/A'
    
    # Thông tin kỹ thuật
    try: info['SliceThickness'] = f"{dcm.SliceThickness:.2f} mm"
    except: info['SliceThickness'] = 'N/A'
    
    try: info['PixelSpacing'] = f"{dcm.PixelSpacing[0]:.2f} x {dcm.PixelSpacing[1]:.2f} mm"
    except: info['PixelSpacing'] = 'N/A'
    
    try: info['ImageType'] = str(dcm.ImageType)
    except: info['ImageType'] = 'N/A'
    
    try: info['TotalSlices'] = ''  # Sẽ được cập nhật sau
    except: info['TotalSlices'] = 'N/A'
    
    return info

def normalize_pixel_array(pixel_array, dcm):
    """Chuẩn hóa giá trị pixel để hiển thị tốt hơn"""
    # Xử lý RescaleSlope và RescaleIntercept nếu có
    try:
        pixel_array = pixel_array * float(dcm.RescaleSlope) + float(dcm.RescaleIntercept)
    except:
        pass
    
    # Chuẩn hóa cho hiển thị
    min_val = np.min(pixel_array)
    max_val = np.max(pixel_array)
    
    # Thiết lập cửa sổ Hounsfield Units nếu có thể
    try:
        window_center = float(dcm.WindowCenter)
        window_width = float(dcm.WindowWidth)
        pixel_array = np.clip(pixel_array, window_center - window_width/2, window_center + window_width/2)
    except:
        # Nếu không có thông tin cửa sổ, sử dụng phương pháp chuẩn hóa thông thường
        pass
    
    # Chuẩn hóa về khoảng [0, 1] để hiển thị
    if max_val != min_val:
        pixel_array = (pixel_array - min_val) / (max_val - min_val)
    
    return pixel_array

class DicomViewer:
    def __init__(self, ct_planning_paths, cbct_paths):
        """Khởi tạo trình xem DICOM với đường dẫn đến ảnh CT và CBCT"""
        self.ct_planning_slices = load_dicom_series(ct_planning_paths)
        self.cbct_slices = load_dicom_series(cbct_paths)
        
        # Kiểm tra xem có ảnh nào được tải không
        if not self.ct_planning_slices and not self.cbct_slices:
            print("Không thể tải bất kỳ ảnh DICOM nào!")
            sys.exit(1)
        
        # Thiết lập chỉ mục lát cắt hiện tại
        self.ct_planning_idx = 0 if self.ct_planning_slices else None
        self.cbct_idx = 0 if self.cbct_slices else None
        
        # Lấy thông tin từ DICOM đầu tiên của mỗi loại (nếu có)
        if self.ct_planning_slices:
            self.ct_planning_info = extract_dicom_info(self.ct_planning_slices[0])
            self.ct_planning_info['TotalSlices'] = len(self.ct_planning_slices)
        
        if self.cbct_slices:
            self.cbct_info = extract_dicom_info(self.cbct_slices[0])
            self.cbct_info['TotalSlices'] = len(self.cbct_slices)
        
        # Tạo giao diện matplotlib
        self.create_ui()
    
    def create_ui(self):
        """Tạo giao diện người dùng với matplotlib"""
        self.fig, self.axes = plt.subplots(1, 2, figsize=(15, 8))
        plt.subplots_adjust(bottom=0.25)  # Để lại không gian cho các điều khiển
        
        # Tiêu đề
        self.fig.suptitle("So sánh ảnh CT lập kế hoạch và CBCT", fontsize=16)
        
        # Thiết lập trục ảnh
        self.axes[0].set_title("CT lập kế hoạch điều trị")
        self.axes[1].set_title("CBCT kiểm tra")
        
        # Vô hiệu hóa trục
        for ax in self.axes:
            ax.set_xticks([])
            ax.set_yticks([])
        
        # Hiển thị ảnh đầu tiên
        self.ct_img = self.axes[0].imshow(np.zeros((512, 512)), cmap='gray')
        self.cbct_img = self.axes[1].imshow(np.zeros((512, 512)), cmap='gray')
        
        # Thêm thanh trượt cho CT lập kế hoạch
        ax_ct_slider = plt.axes([0.1, 0.1, 0.35, 0.03])
        ct_max = len(self.ct_planning_slices) - 1 if self.ct_planning_slices else 0
        self.ct_slider = Slider(ax_ct_slider, 'CT Slice', 0, ct_max, valinit=self.ct_planning_idx or 0, valstep=1)
        self.ct_slider.on_changed(self.update_ct_slice)
        
        # Thêm thanh trượt cho CBCT
        ax_cbct_slider = plt.axes([0.55, 0.1, 0.35, 0.03])
        cbct_max = len(self.cbct_slices) - 1 if self.cbct_slices else 0
        self.cbct_slider = Slider(ax_cbct_slider, 'CBCT Slice', 0, cbct_max, valinit=self.cbct_idx or 0, valstep=1)
        self.cbct_slider.on_changed(self.update_cbct_slice)
        
        # Thêm nút đồng bộ hóa
        ax_sync = plt.axes([0.45, 0.05, 0.1, 0.03])
        self.sync_button = Button(ax_sync, 'Đồng bộ')
        self.sync_button.on_clicked(self.sync_slices)
        
        # Thêm nút lưu ảnh
        ax_save = plt.axes([0.45, 0.01, 0.1, 0.03])
        self.save_button = Button(ax_save, 'Lưu ảnh')
        self.save_button.on_clicked(self.save_current_view)
        
        # Hiển thị thông tin hình ảnh
        self.ct_info_text = self.fig.text(0.1, 0.85, "", fontsize=9, transform=self.fig.transFigure)
        self.cbct_info_text = self.fig.text(0.55, 0.85, "", fontsize=9, transform=self.fig.transFigure)
        
        # Cập nhật hiển thị ban đầu
        self.update_ct_slice(self.ct_planning_idx or 0)
        self.update_cbct_slice(self.cbct_idx or 0)
    
    def update_ct_slice(self, val):
        """Cập nhật hiển thị lát cắt CT khi thanh trượt thay đổi"""
        if not self.ct_planning_slices:
            return
        
        idx = int(val)
        if idx >= len(self.ct_planning_slices):
            idx = len(self.ct_planning_slices) - 1
        
        self.ct_planning_idx = idx
        dcm = self.ct_planning_slices[idx]
        
        # Lấy dữ liệu pixel và chuẩn hóa
        try:
            pixel_array = dcm.pixel_array
            pixel_array = normalize_pixel_array(pixel_array, dcm)
            self.ct_img.set_data(pixel_array)
            self.ct_img.set_clim(vmin=0, vmax=1)
        except Exception as e:
            print(f"Lỗi khi hiển thị CT slice {idx}: {e}")
        
        # Cập nhật thông tin
        info = extract_dicom_info(dcm)
        info['TotalSlices'] = f"{idx+1}/{len(self.ct_planning_slices)}"
        
        # Tạo chuỗi thông tin
        info_str = f"Patient ID: {info['PatientID']}\n"
        info_str += f"Study Date: {info['StudyDate']}\n"
        info_str += f"Acquisition Date: {info['AcquisitionDate']}\n"
        info_str += f"Series Description: {info['SeriesDescription']}\n"
        info_str += f"Slice Thickness: {info['SliceThickness']}\n"
        info_str += f"Slice: {info['TotalSlices']}"
        
        self.ct_info_text.set_text(info_str)
        self.fig.canvas.draw_idle()
    
    def update_cbct_slice(self, val):
        """Cập nhật hiển thị lát cắt CBCT khi thanh trượt thay đổi"""
        if not self.cbct_slices:
            return
        
        idx = int(val)
        if idx >= len(self.cbct_slices):
            idx = len(self.cbct_slices) - 1
        
        self.cbct_idx = idx
        dcm = self.cbct_slices[idx]
        
        # Lấy dữ liệu pixel và chuẩn hóa
        try:
            pixel_array = dcm.pixel_array
            pixel_array = normalize_pixel_array(pixel_array, dcm)
            self.cbct_img.set_data(pixel_array)
            self.cbct_img.set_clim(vmin=0, vmax=1)
        except Exception as e:
            print(f"Lỗi khi hiển thị CBCT slice {idx}: {e}")
        
        # Cập nhật thông tin
        info = extract_dicom_info(dcm)
        info['TotalSlices'] = f"{idx+1}/{len(self.cbct_slices)}"
        
        # Tạo chuỗi thông tin
        info_str = f"Patient ID: {info['PatientID']}\n"
        info_str += f"Study Date: {info['StudyDate']}\n"
        info_str += f"Acquisition Date: {info['AcquisitionDate']}\n"
        info_str += f"Series Description: {info['SeriesDescription']}\n"
        info_str += f"Slice Thickness: {info['SliceThickness']}\n"
        info_str += f"Slice: {info['TotalSlices']}"
        
        self.cbct_info_text.set_text(info_str)
        self.fig.canvas.draw_idle()
    
    def sync_slices(self, event):
        """Đồng bộ hóa vị trí tương đối của lát cắt giữa CT và CBCT"""
        if not self.ct_planning_slices or not self.cbct_slices:
            return
        
        # Tính tỷ lệ vị trí hiện tại của CT
        ct_ratio = self.ct_planning_idx / (len(self.ct_planning_slices) - 1) if len(self.ct_planning_slices) > 1 else 0
        
        # Tính vị trí tương ứng trên CBCT
        cbct_idx = int(ct_ratio * (len(self.cbct_slices) - 1))
        
        # Cập nhật thanh trượt và hiển thị
        self.cbct_slider.set_val(cbct_idx)
        self.update_cbct_slice(cbct_idx)
    
    def save_current_view(self, event):
        """Lưu hiển thị hiện tại thành một tệp hình ảnh"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comparison_{timestamp}.png"
        
        # Lưu hình ảnh hiện tại
        self.fig.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Đã lưu hình ảnh so sánh tại: {filename}")

def main():
    if len(sys.argv) != 3:
        print("Sử dụng: python visualize_classification.py <ct_planning_txt_file> <cbct_txt_file>")
        sys.exit(1)
    
    ct_planning_txt = sys.argv[1]
    cbct_txt = sys.argv[2]
    
    # Kiểm tra sự tồn tại của các file txt
    if not os.path.exists(ct_planning_txt):
        print(f"Không tìm thấy file: {ct_planning_txt}")
        sys.exit(1)
    
    if not os.path.exists(cbct_txt):
        print(f"Không tìm thấy file: {cbct_txt}")
        sys.exit(1)
    
    # Đọc đường dẫn file DICOM từ các file txt
    ct_planning_paths = load_dicom_paths_from_txt(ct_planning_txt)
    cbct_paths = load_dicom_paths_from_txt(cbct_txt)
    
    print(f"Đã tìm thấy {len(ct_planning_paths)} file CT lập kế hoạch và {len(cbct_paths)} file CBCT")
    
    # Tạo và hiển thị trình xem DICOM
    viewer = DicomViewer(ct_planning_paths, cbct_paths)
    plt.show()

if __name__ == "__main__":
    main()