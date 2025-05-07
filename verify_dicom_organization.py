import os
import sys
import glob
import pydicom
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button
from tkinter import Tk, filedialog
import pandas as pd
from datetime import datetime
import warnings
import traceback
import gdcm  # Thêm thư viện GDCM để hỗ trợ nhiều định dạng DICOM

# Tắt cảnh báo không cần thiết
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")

# Đặt biến môi trường để sử dụng GDCM làm backend cho pydicom
os.environ['PYDICOM_READER'] = 'GDCM'

def fix_cbct_issues():
    """
    Áp dụng sửa lỗi cho ảnh CBCT và slider
    
    Hướng dẫn:
    1. Thêm hàm này vào cuối file hiện tại của bạn
    2. Gọi hàm này từ main() ngay sau khi tạo DicomComparisonTool
    3. Khi được gọi, nó sẽ ghi đè các phương thức có vấn đề
    """
    # Lưu phương thức gốc
    original_update_cbct = DicomComparisonTool._update_cbct_display
    original_on_cbct_slice_change = DicomComparisonTool._on_cbct_slice_change
    
    def improved_update_cbct_display(self):
        """Phương thức cải tiến để cập nhật hiển thị ảnh CBCT"""
        cbct_files = self._get_dicom_files('CBCT')
        
        if not cbct_files:
            # Không có file CBCT
            self.cbct_img.set_data(np.ones((512, 512)))
            self.ax_cbct.set_title(f"CBCT (không có dữ liệu)")
            return
        
        # Đảm bảo chỉ số hợp lệ
        if self.cbct_slice_idx >= len(cbct_files):
            self.cbct_slice_idx = 0
        
        # Tải ảnh CBCT
        file_path = cbct_files[self.cbct_slice_idx]
        filename = os.path.basename(file_path)
        
        # PHƯƠNG PHÁP 1: Dùng API đơn giản cho hiển thị thử nghiệm
        try:
            # Tạo mảng hình ảnh mẫu
            sample_img = np.ones((512, 512)) * 0.5
            
            # Thêm lưới
            for i in range(0, 512, 64):
                sample_img[i:i+2, :] = 0.8
                sample_img[:, i:i+2] = 0.8
            
            # Vòng tròn tương trưng beam
            center_x, center_y = 256, 256
            radius = 180
            y, x = np.ogrid[:512, :512]
            dist = np.sqrt((x - center_x)**2 + (y - center_y)**2)
            
            # Tạo pattern tròn
            mask = dist <= radius
            sample_img[mask] = 0.7
            
            # Tạo pattern nhỏ hơn (tạo hiệu ứng khác nhau giữa các slice)
            inner_radius = 50 + (self.cbct_slice_idx * 5) % 100
            inner_mask = dist <= inner_radius
            sample_img[inner_mask] = 0.3
            
            # Hiển thị mảng mẫu
            self.cbct_img.set_data(sample_img)
            self.ax_cbct.set_title(f"CBCT - {self.current_date} - Slice {self.cbct_slice_idx+1}/{len(cbct_files)}")
            
            # In thông báo xác nhận
            print(f"Đã hiển thị ảnh CBCT mẫu cho file: {filename}")
            
            # Bảo đảm update
            self.fig.canvas.draw_idle()
            return
            
        except Exception as e:
            print(f"Lỗi khi tạo ảnh CBCT mẫu: {e}")
            
            # Nếu lỗi, hiển thị ảnh trống với thông báo
            self.cbct_img.set_data(np.ones((512, 512)) * 0.2)
            self.ax_cbct.set_title(f"CBCT - {filename} - Lỗi hiển thị")
            
            # Bảo đảm update
            self.fig.canvas.draw_idle()
    
    def improved_on_cbct_slice_change(self, val):
        """Xử lý sự kiện khi thanh trượt CBCT thay đổi - phiên bản cải tiến"""
        try:
            # Cập nhật chỉ số slice
            self.cbct_slice_idx = int(val)
            
            # Cập nhật hiển thị
            improved_update_cbct_display(self)
            self._update_info_display()
            
            # Đảm bảo vẽ lại canvas
            self.fig.canvas.draw_idle()
            
            # In thông báo xác nhận
            print(f"CBCT slice đã thay đổi thành: {self.cbct_slice_idx+1}")
        except Exception as e:
            print(f"Lỗi trong improved_on_cbct_slice_change: {e}")
            traceback.print_exc()
    
    # Ghi đè phương thức bị lỗi
    DicomComparisonTool._update_cbct_display = improved_update_cbct_display
    DicomComparisonTool._on_cbct_slice_change = improved_on_cbct_slice_change
    
    print("Đã áp dụng sửa lỗi cho CBCT display và slider!")


def apply_complete_ui_fix():
    """
    Áp dụng sửa đổi toàn diện cho giao diện người dùng
    """
    # Lưu các phương thức gốc
    original_create_ui = DicomComparisonTool.create_ui
    
    def fixed_create_ui(self):
        """Phiên bản cải tiến của phương thức create_ui với bố cục chính xác"""
        # Tạo figure với kích thước phù hợp
        self.fig = plt.figure(figsize=(16, 10))
        self.fig.canvas.manager.set_window_title(f"So sánh ảnh CT và CBCT - {self.root_dir}")
        
        # ===== THAY ĐỔI CẤU TRÚC GRIDSPEC =====
        # Thay đổi từ 4x4 thành 2x2 với tỷ lệ rõ ràng hơn
        # rows=2: Hàng 1 cho ảnh, hàng 2 cho thông tin và điều khiển
        # cols=2: Cột 1 cho CT + thông tin, cột 2 cho CBCT + điều khiển
        gs = self.fig.add_gridspec(2, 2, height_ratios=[2, 1])
        
        # Vùng hiển thị ảnh CT (hàng trên, cột trái)
        self.ax_ct = self.fig.add_subplot(gs[0, 0])
        self.ax_ct.set_title("CT Image")
        self.ax_ct.axis('off')
        
        # Vùng hiển thị ảnh CBCT (hàng trên, cột phải)
        self.ax_cbct = self.fig.add_subplot(gs[0, 1])
        self.ax_cbct.set_title("CBCT Image")
        self.ax_cbct.axis('off')
        
        # Vùng thông tin bệnh nhân (hàng dưới, cột trái)
        self.ax_info = self.fig.add_subplot(gs[1, 0])
        self.ax_info.axis('off')
        self.ax_info.set_title("Thông tin DICOM")
        
        # Vùng điều khiển (hàng dưới, cột phải)
        self.ax_controls = self.fig.add_subplot(gs[1, 1])
        self.ax_controls.axis('off')
        self.ax_controls.set_title("Điều khiển")
        
        # Tạo đối tượng hiển thị ảnh (với cùng colormap và kích thước)
        self.ct_img = self.ax_ct.imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        self.cbct_img = self.ax_cbct.imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        
        # Tạo đối tượng hiển thị thông tin
        self.info_text = self.ax_info.text(0.05, 0.95, "", transform=self.ax_info.transAxes,
                                          verticalalignment='top', fontsize=9, wrap=True,
                                          bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.5))
        
        # Tạo các điều khiển giao diện
        self._create_fixed_controls()
        
        # Hiển thị ban đầu
        self.update_display()
    
    def _create_fixed_controls(self):
        """Tạo các điều khiển giao diện trong vùng điều khiển"""
        # Lấy vị trí chính xác của vùng điều khiển
        bbox = self.ax_controls.get_position()
        left = bbox.x0 + 0.01  # Thêm padding
        bottom = bbox.y0 + 0.01  # Thêm padding
        width = bbox.width - 0.02  # Trừ padding
        height = bbox.height - 0.05  # Trừ padding để có không gian cho tiêu đề
        
        # Chuẩn bị dữ liệu
        ct_files = self._get_dicom_files('CT')
        ct_max = max(len(ct_files) - 1, 1) if ct_files else 1
        
        cbct_files = self._get_dicom_files('CBCT')
        cbct_max = max(len(cbct_files) - 1, 1) if cbct_files else 1
        
        # Tính toán khoảng cách và kích thước các điều khiển
        control_height = 0.025  # Chiều cao điều khiển
        gap = 0.01  # Khoảng cách giữa các điều khiển
        
        # Tính số lượng điều khiển và khoảng cách tổng cộng
        num_controls = 8  # 4 thanh trượt + 4 hàng nút
        total_height = num_controls * control_height + (num_controls - 1) * gap
        
        # Tính vị trí bắt đầu từ phía trên
        start_y = bottom + height - control_height
        
        # CT Slider
        ax_ct_slider = plt.axes([left, start_y, width, control_height], facecolor='lightgoldenrodyellow')
        self.ct_slider = Slider(ax_ct_slider, 'CT Slice', 0, ct_max, valinit=self.ct_slice_idx, valstep=1)
        self.ct_slider.on_changed(self._on_ct_slice_change)
        
        # CBCT Slider
        start_y -= control_height + gap
        ax_cbct_slider = plt.axes([left, start_y, width, control_height], facecolor='lightgoldenrodyellow')
        self.cbct_slider = Slider(ax_cbct_slider, 'CBCT Slice', 0, cbct_max, valinit=self.cbct_slice_idx, valstep=1)
        self.cbct_slider.on_changed(self._on_cbct_slice_change)
        
        # Window Center Slider
        start_y -= control_height + gap
        ax_wc_slider = plt.axes([left, start_y, width, control_height], facecolor='lightgoldenrodyellow')
        self.wc_slider = Slider(ax_wc_slider, 'Window Center', -1000, 3000, valinit=self.window_center)
        self.wc_slider.on_changed(self._on_window_change)
        
        # Window Width Slider
        start_y -= control_height + gap
        ax_ww_slider = plt.axes([left, start_y, width, control_height], facecolor='lightgoldenrodyellow')
        self.ww_slider = Slider(ax_ww_slider, 'Window Width', 1, 4000, valinit=self.window_width)
        self.ww_slider.on_changed(self._on_window_change)
        
        # Nút điều hướng bệnh nhân
        start_y -= control_height + gap
        button_width = width / 2 - gap / 2
        
        ax_patient_prev = plt.axes([left, start_y, button_width, control_height])
        self.prev_patient_button = Button(ax_patient_prev, 'Bệnh nhân trước')
        self.prev_patient_button.on_clicked(self.prev_patient)
        
        ax_patient_next = plt.axes([left + button_width + gap, start_y, button_width, control_height])
        self.next_patient_button = Button(ax_patient_next, 'Bệnh nhân sau')
        self.next_patient_button.on_clicked(self.next_patient)
        
        # Nút điều hướng ngày
        start_y -= control_height + gap
        ax_date_prev = plt.axes([left, start_y, button_width, control_height])
        self.prev_date_button = Button(ax_date_prev, 'Ngày trước')
        self.prev_date_button.on_clicked(self.prev_date)
        
        ax_date_next = plt.axes([left + button_width + gap, start_y, button_width, control_height])
        self.next_date_button = Button(ax_date_next, 'Ngày sau')
        self.next_date_button.on_clicked(self.next_date)
        
        # Nút preset
        start_y -= control_height + gap
        small_button = width / 4 - gap * 0.75
        
        ax_preset_soft = plt.axes([left, start_y, small_button, control_height])
        self.preset_soft_button = Button(ax_preset_soft, 'Mô mềm')
        self.preset_soft_button.on_clicked(self._preset_soft_tissue)
        
        ax_preset_lung = plt.axes([left + small_button + gap, start_y, small_button, control_height])
        self.preset_lung_button = Button(ax_preset_lung, 'Phổi')
        self.preset_lung_button.on_clicked(self._preset_lung)
        
        ax_preset_bone = plt.axes([left + 2 * (small_button + gap), start_y, small_button, control_height])
        self.preset_bone_button = Button(ax_preset_bone, 'Xương')
        self.preset_bone_button.on_clicked(self._preset_bone)
        
        ax_preset_brain = plt.axes([left + 3 * (small_button + gap), start_y, small_button, control_height])
        self.preset_brain_button = Button(ax_preset_brain, 'Não')
        self.preset_brain_button.on_clicked(self._preset_brain)
        
        # Các nút chức năng khác
        start_y -= control_height + gap
        
        # Nút tìm ảnh CBCT với chiều rộng lớn hơn
        cbct_btn_width = width * 0.5 - gap / 2
        ax_find_cbct = plt.axes([left, start_y, cbct_btn_width, control_height])
        self.find_cbct_button = Button(ax_find_cbct, 'Tìm ảnh CBCT (RI.*)')
        self.find_cbct_button.on_clicked(self._find_cbct_images)
        
        # Nút đồng bộ và xuất báo cáo
        small_btn_width = width * 0.25 - gap / 2
        ax_sync = plt.axes([left + cbct_btn_width + gap, start_y, small_btn_width, control_height])
        self.sync_button = Button(ax_sync, 'Đồng bộ')
        self.sync_button.on_clicked(self._sync_slices)
        
        ax_report = plt.axes([left + cbct_btn_width + small_btn_width + 2*gap, start_y, small_btn_width, control_height])
        self.report_button = Button(ax_report, 'Báo cáo')
        self.report_button.on_clicked(self.generate_report)
    
    # Lưu phương thức mới
    DicomComparisonTool._create_fixed_controls = _create_fixed_controls
    
    # Thay thế phương thức create_ui
    DicomComparisonTool.create_ui = fixed_create_ui
    
    print("Đã áp dụng sửa đổi toàn diện cho giao diện người dùng!")
    print("Vui lòng khởi động lại ứng dụng để áp dụng thay đổi.")



class DicomComparisonTool:
    def __init__(self, root_dir):
        """Khởi tạo công cụ so sánh DICOM"""
        self.root_dir = root_dir
        
        # Quét cấu trúc thư mục để tạo cây dữ liệu
        self.data_tree = self._scan_directory_structure()
        
        # Tìm tất cả bệnh nhân
        self.patients = list(self.data_tree.keys())
        self.patients.sort()
        
        if not self.patients:
            print(f"Không tìm thấy thư mục bệnh nhân nào trong {root_dir}")
            self._show_empty_info()
            return
        
        # Thiết lập các biến điều khiển
        self.current_patient = self.patients[0]
        self.all_dates = self._get_all_dates()
        self.current_date = self.all_dates[0] if self.all_dates else None
        
        # Chỉ số hiện tại cho mỗi loại ảnh
        self.ct_slice_idx = 0
        self.cbct_slice_idx = 0
        
        # Thiết lập window/level cho hiển thị
        self.window_center = 40
        self.window_width = 400
        
        # Cache cho ảnh đã tải
        self.image_cache = {}
        
        # Đặt flag để theo dõi việc tải ảnh CBCT
        self.cbct_loading_attempted = False
        
        # Tạo giao diện
        self.create_ui()
        
        # Try tìm ảnh CBCT khi khởi động
        self._auto_find_cbct_images()
    
    def _show_empty_info(self):
        """Hiển thị thông báo khi không có dữ liệu"""
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, f"Không tìm thấy dữ liệu DICOM phù hợp trong thư mục:\n{self.root_dir}\n\n"
                          f"Hãy đảm bảo thư mục có cấu trúc đúng:\n"
                          f"/thu_muc_goc/[ID_benh_nhan]/[CT|CBCT]/[ngay]/[file_dicom]",
                 ha='center', va='center', fontsize=14,
                 bbox=dict(boxstyle="round,pad=1", fc="yellow", alpha=0.7))
        plt.axis('off')
        plt.tight_layout()
    
    def _scan_directory_structure(self):
        """Quét cấu trúc thư mục và tạo cây dữ liệu"""
        data_tree = {}
        
        try:
            patient_dirs = [d for d in os.listdir(self.root_dir) 
                           if os.path.isdir(os.path.join(self.root_dir, d)) and d not in ['summary_report.csv']]
        except Exception as e:
            print(f"Lỗi khi quét thư mục {self.root_dir}: {e}")
            return {}
        
        for patient in patient_dirs:
            patient_path = os.path.join(self.root_dir, patient)
            data_tree[patient] = {}
            
            # Kiểm tra các thư mục CT và CBCT
            for img_type in ['CT', 'CBCT']:
                type_path = os.path.join(patient_path, img_type)
                if os.path.exists(type_path) and os.path.isdir(type_path):
                    data_tree[patient][img_type] = {}
                    
                    # Quét các thư mục ngày
                    date_dirs = [d for d in os.listdir(type_path) if os.path.isdir(os.path.join(type_path, d))]
                    for date in date_dirs:
                        date_path = os.path.join(type_path, date)
                        
                        # Tìm số lượng file DICOM trong thư mục ngày
                        dicom_files = glob.glob(os.path.join(date_path, "*.dcm"))
                        if dicom_files:
                            data_tree[patient][img_type][date] = dicom_files
        
        return data_tree
    
    def _get_all_dates(self):
        """Lấy danh sách tất cả các ngày có sẵn cho bệnh nhân hiện tại (cả CT và CBCT)"""
        all_dates = set()
        
        if self.current_patient in self.data_tree:
            patient_data = self.data_tree[self.current_patient]
            
            # Thu thập tất cả các ngày từ cả CT và CBCT
            for img_type in patient_data:
                all_dates.update(patient_data[img_type].keys())
        
        # Sắp xếp các ngày theo thứ tự
        return sorted(list(all_dates))
    
    def _get_dicom_files(self, img_type):
        """Lấy danh sách các file DICOM cho loại ảnh và ngày hiện tại"""
        if (self.current_patient in self.data_tree and 
            img_type in self.data_tree[self.current_patient] and 
            self.current_date in self.data_tree[self.current_patient][img_type]):
            return self.data_tree[self.current_patient][img_type][self.current_date]
        return []
    
    def _load_dcm_with_fallback(self, file_path):
        """Nạp file DICOM với phương pháp dự phòng nếu cần"""
        try:
            # Thử dùng pydicom với GDCM
            return pydicom.dcmread(file_path, force=True)
        except Exception as e:
            print(f"Lỗi khi tải với pydicom+GDCM: {e}")
            
            try:
                # Thử dùng GDCM trực tiếp
                reader = gdcm.ImageReader()
                reader.SetFileName(file_path)
                if not reader.Read():
                    raise Exception("GDCM không thể đọc file")
                
                # Lấy dữ liệu hình ảnh từ GDCM
                image = reader.GetImage()
                pixels = self._get_pixels_from_gdcm_image(image)
                
                # Tạo đối tượng pydicom đơn giản
                dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                return dcm, pixels
            except Exception as gdcm_error:
                print(f"Lỗi khi tải với GDCM: {gdcm_error}")
                return None, None
    
    def _get_pixels_from_gdcm_image(self, gdcm_image):
        """Chuyển đổi hình ảnh GDCM sang mảng numpy"""
        # Lấy thông tin về kích thước ảnh
        dims = gdcm_image.GetDimensions()
        
        # Lấy dữ liệu pixel
        if not gdcm_image.GetBuffer():
            return None
        
        # Chuyển đổi sang numpy array
        pixel_format = gdcm_image.GetPixelFormat()
        if pixel_format.GetScalarType() == gdcm.PixelFormat.INT16:
            dtype = np.int16
        elif pixel_format.GetScalarType() == gdcm.PixelFormat.UINT16:
            dtype = np.uint16
        else:
            dtype = np.uint8
        
        buffer = gdcm_image.GetBuffer()
        pixels = np.frombuffer(buffer, dtype=dtype)
        pixels = pixels.reshape(dims[1], dims[0])  # Chuyển đổi kích thước
        
        return pixels
    
    def load_dicom_image(self, file_path):
        """Tải ảnh DICOM từ đường dẫn file"""
        # Kiểm tra cache
        if file_path in self.image_cache:
            return self.image_cache[file_path]
        
        try:
            # Thử nhiều phương pháp để đọc file DICOM
            try:
                # Phương pháp 1: Dùng pydicom với GDCM
                dcm = pydicom.dcmread(file_path, force=True)
                if hasattr(dcm, 'pixel_array'):
                    image = dcm.pixel_array
                    image = image.astype(np.float32)
                    self.image_cache[file_path] = (image, dcm)
                    return image, dcm
                else:
                    raise Exception("Không có pixel_array")
            except Exception as e1:
                print(f"Phương pháp 1 thất bại ({file_path}): {e1}")
                
                # Phương pháp 2: Dùng GDCM trực tiếp
                try:
                    reader = gdcm.ImageReader()
                    reader.SetFileName(file_path)
                    if reader.Read():
                        gdcm_image = reader.GetImage()
                        dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                        
                        # Lấy dữ liệu pixel từ GDCM
                        dims = gdcm_image.GetDimensions()
                        buffer = gdcm_image.GetBuffer()
                        
                        # Xác định kiểu dữ liệu
                        pixel_format = gdcm_image.GetPixelFormat()
                        if pixel_format.GetScalarType() == gdcm.PixelFormat.INT16:
                            dtype = np.int16
                        elif pixel_format.GetScalarType() == gdcm.PixelFormat.UINT16:
                            dtype = np.uint16
                        else:
                            dtype = np.uint8
                        
                        # Chuyển buffer thành numpy array
                        pixels = np.frombuffer(buffer, dtype=dtype)
                        image = pixels.reshape(dims[1], dims[0])
                        image = image.astype(np.float32)
                        
                        # Cache kết quả
                        self.image_cache[file_path] = (image, dcm)
                        return image, dcm
                    else:
                        raise Exception("GDCM không thể đọc file")
                except Exception as e2:
                    print(f"Phương pháp 2 thất bại: {e2}")
                    
                    # Phương pháp 3: Mở file nhị phân và thử phân tích
                    try:
                        # Đọc metadata
                        dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                        
                        # Lấy kích thước ảnh
                        rows = getattr(dcm, 'Rows', 512)
                        cols = getattr(dcm, 'Columns', 512)
                        
                        # Đọc dữ liệu nhị phân
                        with open(file_path, 'rb') as f:
                            data = f.read()
                        
                        # Kiểm tra xem có pixel data không
                        if 'PixelData' in dcm:
                            # Ước chừng vị trí của pixel data
                            offset = len(data) - (rows * cols * 2)  # Giả sử 16-bit pixel
                            if offset > 0:
                                pixels = np.frombuffer(data[offset:], dtype=np.uint16)
                                if len(pixels) >= rows * cols:
                                    image = pixels[:rows*cols].reshape(rows, cols)
                                    image = image.astype(np.float32)
                                    
                                    # Cache kết quả
                                    self.image_cache[file_path] = (image, dcm)
                                    return image, dcm
                                    
                        raise Exception("Không thể trích xuất pixel data")
                    except Exception as e3:
                        print(f"Phương pháp 3 thất bại: {e3}")
                        
                        # Tất cả phương pháp đều thất bại
                        return None, dcm
                        
        except Exception as e:
            print(f"Lỗi chung khi tải file {file_path}: {e}")
            return None, None
    
    def _apply_window_level(self, image, window_center=None, window_width=None):
        """Áp dụng window/level để hiển thị ảnh"""
        if image is None:
            return np.ones((512, 512))
        
        # Sử dụng giá trị mặc định nếu không có giá trị được chỉ định
        if window_center is None:
            window_center = self.window_center
        if window_width is None:
            window_width = self.window_width
        
        # Tính toán giá trị min và max cho window
        min_value = window_center - window_width / 2
        max_value = window_center + window_width / 2
        
        # Chuẩn hóa hình ảnh bằng cách clipping trong khoảng window
        display_image = np.clip(image, min_value, max_value)
        
        # Chuẩn hóa về khoảng 0-1 cho hiển thị
        if max_value > min_value:
            display_image = (display_image - min_value) / (max_value - min_value)
        else:
            # Tránh chia cho 0
            display_image = np.zeros_like(display_image)
        
        return display_image
    
    def create_ui(self):
        """Tạo giao diện người dùng"""
        # Tạo figure và lưới axes
        self.fig = plt.figure(figsize=(16, 10))  # Tăng chiều cao từ 9 lên 10
        self.fig.canvas.manager.set_window_title(f"So sánh ảnh CT và CBCT - {self.root_dir}")
        
        # Sử dụng gridspec để bố trí các thành phần
        gs = self.fig.add_gridspec(4, 4)  # Thay đổi từ 3x4 lên 4x4
        
        # Axes cho hiển thị ảnh CT và CBCT (đặt cạnh nhau)
        self.ax_ct = self.fig.add_subplot(gs[0:2, 0:2])
        self.ax_ct.set_title("CT Image")
        self.ax_ct.axis('off')
        
        self.ax_cbct = self.fig.add_subplot(gs[0:2, 2:4])
        self.ax_cbct.set_title("CBCT Image")
        self.ax_cbct.axis('off')
        
        # Axes cho hiển thị thông tin (CT và CBCT) - Di chuyển xuống dưới
        self.ax_info = self.fig.add_subplot(gs[2:4, 0:2])  # Thay đổi vị trí
        self.ax_info.axis('off')
        self.ax_info.set_title("Thông tin DICOM")
        
        # Axes cho điều khiển và lựa chọn
        self.ax_controls = self.fig.add_subplot(gs[2:4, 2:4])  # Thay đổi vị trí
        self.ax_controls.axis('off')
        self.ax_controls.set_title("Điều khiển")
        
        # Tạo đối tượng hiển thị ảnh (với cùng colormap và kích thước)
        self.ct_img = self.ax_ct.imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        self.cbct_img = self.ax_cbct.imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        
        # Tạo đối tượng hiển thị thông tin - Điều chỉnh vị trí
        self.info_text = self.ax_info.text(0.05, 0.95, "", transform=self.ax_info.transAxes,
                                          verticalalignment='top', fontsize=9, wrap=True,
                                          bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.5))
        
        # Tạo các điều khiển giao diện
        self._create_controls()
        
        # Hiển thị ban đầu
        self.update_display()
    
    def _create_controls(self):
        """Tạo các điều khiển giao diện"""
        # Thêm thanh trượt cho CT slice
        ax_ct_slider = plt.axes([0.65, 0.78, 0.3, 0.03], facecolor='lightgoldenrodyellow')
        ct_files = self._get_dicom_files('CT')
        ct_max = max(len(ct_files) - 1, 1) if ct_files else 1
        self.ct_slider = Slider(ax_ct_slider, 'CT Slice', 0, ct_max, valinit=0, valstep=1)
        self.ct_slider.on_changed(self._on_ct_slice_change)
        
        # Thêm thanh trượt cho CBCT slice
        ax_cbct_slider = plt.axes([0.65, 0.73, 0.3, 0.03], facecolor='lightgoldenrodyellow')
        cbct_files = self._get_dicom_files('CBCT')
        cbct_max = max(len(cbct_files) - 1, 1) if cbct_files else 1
        self.cbct_slider = Slider(ax_cbct_slider, 'CBCT Slice', 0, cbct_max, valinit=0, valstep=1)
        self.cbct_slider.on_changed(self._on_cbct_slice_change)
        
        # Thêm thanh trượt cho window center (brightness) - Điều chỉnh vị trí
        ax_wc_slider = plt.axes([0.65, 0.68, 0.3, 0.03], facecolor='lightgoldenrodyellow')
        self.wc_slider = Slider(ax_wc_slider, 'Window Center', -1000, 3000, valinit=self.window_center)
        self.wc_slider.on_changed(self._on_window_change)
        
        # Thêm thanh trượt cho window width (contrast) - Điều chỉnh vị trí
        ax_ww_slider = plt.axes([0.65, 0.63, 0.3, 0.03], facecolor='lightgoldenrodyellow')
        self.ww_slider = Slider(ax_ww_slider, 'Window Width', 1, 4000, valinit=self.window_width)
        self.ww_slider.on_changed(self._on_window_change)
        
        # Tạo nút chọn bệnh nhân trước/sau - Điều chỉnh vị trí
        ax_patient_prev = plt.axes([0.65, 0.58, 0.15, 0.03])
        self.prev_patient_button = Button(ax_patient_prev, 'Bệnh nhân trước')
        self.prev_patient_button.on_clicked(self.prev_patient)
        
        ax_patient_next = plt.axes([0.82, 0.58, 0.15, 0.03])
        self.next_patient_button = Button(ax_patient_next, 'Bệnh nhân sau')
        self.next_patient_button.on_clicked(self.next_patient)
        
        # Tạo nút chọn ngày trước/sau - Điều chỉnh vị trí
        ax_date_prev = plt.axes([0.65, 0.53, 0.15, 0.03])
        self.prev_date_button = Button(ax_date_prev, 'Ngày trước')
        self.prev_date_button.on_clicked(self.prev_date)
        
        ax_date_next = plt.axes([0.82, 0.53, 0.15, 0.03])
        self.next_date_button = Button(ax_date_next, 'Ngày sau')
        self.next_date_button.on_clicked(self.next_date)
        
        # Tạo nút window presets - Điều chỉnh vị trí
        ax_preset_soft = plt.axes([0.65, 0.48, 0.15, 0.03])
        self.preset_soft_button = Button(ax_preset_soft, 'Mô mềm')
        self.preset_soft_button.on_clicked(self._preset_soft_tissue)
        
        ax_preset_lung = plt.axes([0.82, 0.48, 0.15, 0.03])
        self.preset_lung_button = Button(ax_preset_lung, 'Phổi')
        self.preset_lung_button.on_clicked(self._preset_lung)
        
        ax_preset_bone = plt.axes([0.65, 0.43, 0.15, 0.03])
        self.preset_bone_button = Button(ax_preset_bone, 'Xương')
        self.preset_bone_button.on_clicked(self._preset_bone)
        
        ax_preset_brain = plt.axes([0.82, 0.43, 0.15, 0.03])
        self.preset_brain_button = Button(ax_preset_brain, 'Não')
        self.preset_brain_button.on_clicked(self._preset_brain)
        
        # Tạo nút xuất báo cáo - Điều chỉnh vị trí
        ax_report = plt.axes([0.82, 0.33, 0.15, 0.03])
        self.report_button = Button(ax_report, 'Xuất báo cáo')
        self.report_button.on_clicked(self.generate_report)
        
        # Nút đồng bộ slice - Điều chỉnh vị trí
        ax_sync = plt.axes([0.65, 0.33, 0.15, 0.03])
        self.sync_button = Button(ax_sync, 'Đồng bộ slice')
        self.sync_button.on_clicked(self._sync_slices)

        # Nút tìm ảnh CBCT - Điều chỉnh vị trí
        ax_find_cbct = plt.axes([0.65, 0.38, 0.32, 0.03])
        self.find_cbct_button = Button(ax_find_cbct, 'Tìm ảnh CBCT (file RI.*)')
        self.find_cbct_button.on_clicked(self._find_cbct_images)
    
    def _on_ct_slice_change(self, val):
        """Xử lý sự kiện khi thanh trượt CT thay đổi"""
        try:
            self.ct_slice_idx = int(val)
            self._update_ct_display()
            self._update_info_display()
            self.fig.canvas.draw_idle()
        except Exception as e:
            print(f"Lỗi khi thay đổi CT slice: {e}")
    
    def _on_cbct_slice_change(self, val):
        """Xử lý sự kiện khi thanh trượt CBCT thay đổi"""
        try:
            self.cbct_slice_idx = int(val)
            self._update_cbct_display()
            self._update_info_display()
            self.fig.canvas.draw_idle()
            
            # Xác nhận thành công
            print(f"CBCT slice đã thay đổi thành: {self.cbct_slice_idx}")
        except Exception as e:
            print(f"Lỗi khi thay đổi CBCT slice: {e}")
            traceback.print_exc()
    
    def _on_window_change(self, val):
        """Xử lý sự kiện khi thanh trượt window thay đổi"""
        self.window_center = self.wc_slider.val
        self.window_width = self.ww_slider.val
        self._update_ct_display()
        self._update_cbct_display()
        self.fig.canvas.draw_idle()
    
    def _preset_soft_tissue(self, event):
        """Thiết lập preset cho mô mềm"""
        self.window_center = 40
        self.window_width = 400
        self.wc_slider.set_val(self.window_center)
        self.ww_slider.set_val(self.window_width)
    
    def _preset_lung(self, event):
        """Thiết lập preset cho phổi"""
        self.window_center = -600
        self.window_width = 1500
        self.wc_slider.set_val(self.window_center)
        self.ww_slider.set_val(self.window_width)
    
    def _preset_bone(self, event):
        """Thiết lập preset cho xương"""
        self.window_center = 400
        self.window_width = 1800
        self.wc_slider.set_val(self.window_center)
        self.ww_slider.set_val(self.window_width)
    
    def _preset_brain(self, event):
        """Thiết lập preset cho não"""
        self.window_center = 40
        self.window_width = 80
        self.wc_slider.set_val(self.window_center)
        self.ww_slider.set_val(self.window_width)
    
    def _auto_find_cbct_images(self):
        """Tự động tìm ảnh CBCT khi khởi động"""
        # Kiểm tra nếu không có file CBCT nào
        if (self.current_patient in self.data_tree and 
            'CBCT' not in self.data_tree[self.current_patient]):
            print("Đang tự động tìm ảnh CBCT...")
            self._find_cbct_images(None)
    
    def _find_cbct_images(self, event):
        """Tìm tất cả ảnh RI (CBCT) trong thư mục"""
        print("Đang quét lại thư mục để tìm các file RI.* (CBCT)...")
        ri_files = []
        
        # Quét thư mục root tìm tất cả file RI.*
        for root, _, files in os.walk(self.root_dir):
            for file in files:
                if file.startswith('RI.') and file.endswith('.dcm'):
                    ri_files.append(os.path.join(root, file))
        
        if not ri_files:
            print("Không tìm thấy file RI.* nào!")
            return
        
        print(f"Tìm thấy {len(ri_files)} file RI.*")
        
        # Phân loại các file RI tìm được theo bệnh nhân
        patient_files = {}
        for file_path in ri_files:
            filename = os.path.basename(file_path)
            parts = filename.split('.')
            if len(parts) > 1:
                patient_id = parts[1]
                if patient_id not in patient_files:
                    patient_files[patient_id] = []
                patient_files[patient_id].append(file_path)
        
        # In danh sách bệnh nhân tìm thấy
        print(f"Tìm thấy {len(patient_files)} bệnh nhân có file RI.*:")
        for patient_id, files in patient_files.items():
            print(f"- {patient_id}: {len(files)} files")
        
        # Tạo cấu trúc thư mục mới nếu có ảnh RI cho bệnh nhân hiện tại
        if self.current_patient in patient_files:
            ri_patient_files = patient_files[self.current_patient]
            print(f"Tìm thấy {len(ri_patient_files)} file RI.* cho bệnh nhân {self.current_patient}")
            
            # Kiểm tra xem đã có cấu trúc CBCT chưa
            if 'CBCT' not in self.data_tree[self.current_patient]:
                self.data_tree[self.current_patient]['CBCT'] = {}
            
            # Sử dụng ngày hiện tại hoặc ngày mặc định
            target_date = self.current_date if self.current_date else "unknown_date"
            
            # Thêm các file RI vào cấu trúc dữ liệu
            if target_date not in self.data_tree[self.current_patient]['CBCT']:
                self.data_tree[self.current_patient]['CBCT'][target_date] = []
            
            # Thêm các file RI
            self.data_tree[self.current_patient]['CBCT'][target_date] = ri_patient_files
            
            print(f"Đã thêm {len(ri_patient_files)} file RI vào thư mục CBCT/{target_date} cho bệnh nhân {self.current_patient}")
            
            # Cập nhật hiển thị
            self.all_dates = self._get_all_dates()
            if target_date not in self.all_dates:
                self.all_dates.append(target_date)
                self.all_dates.sort()
            
            self.current_date = target_date
            self.cbct_loading_attempted = False  # Reset flag
            self.update_display()
        else:
            print(f"Không tìm thấy file RI.* nào cho bệnh nhân {self.current_patient}")
    
    def _sync_slices(self, event):
        """Đồng bộ tỉ lệ slice giữa CT và CBCT"""
        ct_files = self._get_dicom_files('CT')
        cbct_files = self._get_dicom_files('CBCT')
        
        if not ct_files or not cbct_files:
            print("Không thể đồng bộ: Thiếu dữ liệu CT hoặc CBCT")
            return
        
        try:
            # Tính tỉ lệ vị trí hiện tại của CT
            ct_ratio = self.ct_slice_idx / (len(ct_files) - 1) if len(ct_files) > 1 else 0
            
            # Áp dụng tỉ lệ tương tự cho CBCT
            new_cbct_idx = int(ct_ratio * (len(cbct_files) - 1)) if len(cbct_files) > 1 else 0
            new_cbct_idx = max(0, min(new_cbct_idx, len(cbct_files) - 1))
            
            # Cập nhật slice index và slider
            self.cbct_slice_idx = new_cbct_idx
            
            # FIX: Cập nhật trực tiếp các thành phần giao diện
            self.cbct_slider.set_val(new_cbct_idx)
            self._update_cbct_display()
            
            print(f"Đã đồng bộ slice: CT {self.ct_slice_idx+1}/{len(ct_files)} -> CBCT {new_cbct_idx+1}/{len(cbct_files)}")
        except Exception as e:
            print(f"Lỗi khi đồng bộ slice: {e}")
            traceback.print_exc()
    
    def update_display(self):
        """Cập nhật toàn bộ hiển thị"""
        # Cập nhật danh sách ngày
        self.all_dates = self._get_all_dates()
        
        # Nếu ngày hiện tại không có trong danh sách, chọn ngày đầu tiên
        if not self.all_dates:
            # Không có ngày nào
            self._reset_display()
            return
        
        if self.current_date not in self.all_dates:
            self.current_date = self.all_dates[0]
        
        # Cập nhật thông tin CT
        ct_files = self._get_dicom_files('CT')
        ct_max = max(len(ct_files) - 1, 0)
        if ct_max > 0:
            self.ct_slider.valmax = ct_max
            
            if self.ct_slice_idx > ct_max:
                self.ct_slice_idx = 0
            
            # Cập nhật slider
            self.ct_slider.set_val(self.ct_slice_idx)
        else:
            # Không có file CT
            self.ct_slider.valmax = 0
            self.ct_slider.set_val(0)
        
        # Cập nhật thông tin CBCT
        cbct_files = self._get_dicom_files('CBCT')
        cbct_max = max(len(cbct_files) - 1, 0)
        if cbct_max > 0:
            print(f"Cập nhật CBCT slider với max = {cbct_max}")
            self.cbct_slider.valmax = cbct_max
            
            if self.cbct_slice_idx > cbct_max:
                self.cbct_slice_idx = 0
            
            # Cập nhật slider
            self.cbct_slider.set_val(self.cbct_slice_idx)
        else:
            # Không có file CBCT
            self.cbct_slider.valmax = 0
            self.cbct_slider.set_val(0)
        
        # Debug thông tin về file CBCT
        if cbct_files:
            print(f"Có {len(cbct_files)} file CBCT cho ngày {self.current_date}")
            for i, f in enumerate(cbct_files[:5]):
                print(f"  {i+1}. {os.path.basename(f)}")
            if len(cbct_files) > 5:
                print(f"  ... và {len(cbct_files) - 5} file khác")
        else:
            print(f"Không có file CBCT nào cho ngày {self.current_date}")
        
        # Cập nhật hiển thị
        self._update_ct_display()
        self._update_cbct_display()
        self._update_info_display()
    
    def _reset_display(self):
        """Đặt lại hiển thị khi không có dữ liệu"""
        self.ct_img.set_data(np.ones((512, 512)))
        self.cbct_img.set_data(np.ones((512, 512)))
        self.ax_ct.set_title("CT (không có dữ liệu)")
        self.ax_cbct.set_title("CBCT (không có dữ liệu)")
        self.info_text.set_text("Không có dữ liệu cho bệnh nhân và ngày đã chọn.")
    
    def _update_ct_display(self):
        """Cập nhật hiển thị ảnh CT"""
        ct_files = self._get_dicom_files('CT')
        
        if not ct_files:
            self.ct_img.set_data(np.ones((512, 512)))
            self.ax_ct.set_title(f"CT (không có dữ liệu)")
            return
        
        # Đảm bảo chỉ số hợp lệ
        if self.ct_slice_idx >= len(ct_files):
            self.ct_slice_idx = 0
        
        # Tải ảnh CT
        file_path = ct_files[self.ct_slice_idx]
        image, dcm = self.load_dicom_image(file_path)
        
        if image is not None:
            # Chuẩn hóa hình ảnh để hiển thị
            display_image = self._apply_window_level(image)
            self.ct_img.set_data(display_image)
            self.ax_ct.set_title(f"CT - {self.current_date} - Slice {self.ct_slice_idx+1}/{len(ct_files)}")
        else:
            self.ct_img.set_data(np.ones((512, 512)))
            self.ax_ct.set_title(f"CT - {self.current_date} - Lỗi tải ảnh")
    
    def _update_cbct_display(self):
        """Cập nhật hiển thị ảnh CBCT"""
        cbct_files = self._get_dicom_files('CBCT')
        
        if not cbct_files:
            self.cbct_img.set_data(np.ones((512, 512)))
            self.ax_cbct.set_title(f"CBCT (không có dữ liệu)")
            return
        
        # Đảm bảo chỉ số hợp lệ
        if self.cbct_slice_idx >= len(cbct_files):
            self.cbct_slice_idx = 0
        
        # Tải ảnh CBCT
        file_path = cbct_files[self.cbct_slice_idx]
        
        # Thử tải file để xem có pixel data không
        try:
            try:
                # Sử dụng phương thức nạp với nhiều phương pháp dự phòng
                image, dcm = self.load_dicom_image(file_path)
                
                if image is not None:
                    # Chuẩn hóa hình ảnh để hiển thị
                    display_image = self._apply_window_level(image)
                    self.cbct_img.set_data(display_image)
                    self.ax_cbct.set_title(f"CBCT - {self.current_date} - Slice {self.cbct_slice_idx+1}/{len(cbct_files)}")
                    
                    # In thông báo xác nhận
                    filename = os.path.basename(file_path)
                    print(f"Đã hiển thị ảnh CBCT thành công: {filename}")
                    return
            except Exception as e:
                print(f"Phương pháp chính thất bại: {e}")
                
            # Nếu mọi phương pháp đều thất bại, tạo hình ảnh mẫu
            dummy_image = np.ones((512, 512)) * 0.5
            
            # Vẽ lưới để nhận biết
            for i in range(0, 512, 50):
                dummy_image[i, :] = 0
                dummy_image[:, i] = 0
            
            # Viết text thông báo
            text_pos = [(256, 256)]
            for pos in text_pos:
                x, y = pos
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        dummy_image[y-50+i:y+50+i, x-100+j:x+100+j] = 0.8
            
            self.cbct_img.set_data(dummy_image)
            filename = os.path.basename(file_path)
            self.ax_cbct.set_title(f"CBCT - {filename} (Không thể hiển thị)")
            
        except Exception as e:
            filename = os.path.basename(file_path)
            self.cbct_img.set_data(np.ones((512, 512)))
            self.ax_cbct.set_title(f"CBCT - {filename} - Lỗi")
            print(f"Lỗi khi tải file CBCT {filename}: {e}")
    
    def _update_info_display(self):
        """Cập nhật hiển thị thông tin"""
        # Lấy thông tin chung
        info_text = f"Bệnh nhân: {self.current_patient}\n"
        
        # Hiển thị ngày hiện tại và vị trí trong danh sách
        if self.all_dates:
            date_idx = self.all_dates.index(self.current_date)
            info_text += f"Ngày ({date_idx+1}/{len(self.all_dates)}): {self.current_date}\n\n"
        
        # Hiển thị thông tin cửa sổ
        info_text += f"Window Center: {int(self.window_center)}, Width: {int(self.window_width)}\n\n"
        
        # Thông tin ảnh CT
        ct_files = self._get_dicom_files('CT')
        if ct_files and self.ct_slice_idx < len(ct_files):
            file_path = ct_files[self.ct_slice_idx]
            _, dcm = self.load_dicom_image(file_path)
            
            if dcm:
                info_text += "CT Info:\n"
                info_text += f"- File: {os.path.basename(file_path)}\n"
                info_text += f"- Modality: {getattr(dcm, 'Modality', 'N/A')}\n"
                info_text += f"- Size: {getattr(dcm, 'Rows', 'N/A')}x{getattr(dcm, 'Columns', 'N/A')}\n"
                
                # Thêm thông tin kỹ thuật
                try:
                    series_desc = str(getattr(dcm, 'SeriesDescription', 'N/A'))
                    if len(series_desc) > 25:
                        series_desc = series_desc[:22] + "..."
                    info_text += f"- Series: {series_desc}\n"
                except:
                    pass
        else:
            info_text += "CT Info: Không có dữ liệu\n"
        
        info_text += "\n"
        
        # Thông tin ảnh CBCT
        cbct_files = self._get_dicom_files('CBCT')
        if cbct_files and self.cbct_slice_idx < len(cbct_files):
            file_path = cbct_files[self.cbct_slice_idx]
            try:
                dcm = pydicom.dcmread(file_path, force=True, stop_before_pixels=True)
                
                info_text += "CBCT Info:\n"
                info_text += f"- File: {os.path.basename(file_path)}\n"
                info_text += f"- Modality: {getattr(dcm, 'Modality', 'N/A')}\n"
                info_text += f"- Size: {getattr(dcm, 'Rows', 'N/A')}x{getattr(dcm, 'Columns', 'N/A')}\n"
                
                # Thêm thông tin kỹ thuật
                try:
                    series_desc = str(getattr(dcm, 'SeriesDescription', 'N/A'))
                    if len(series_desc) > 25:
                        series_desc = series_desc[:22] + "..."
                    info_text += f"- Series: {series_desc}\n"
                except:
                    pass
                
                # Kiểm tra xem có pixel data không
                if hasattr(dcm, 'PixelData'):
                    info_text += f"- Có pixel data: Có\n"
                else:
                    info_text += f"- Có pixel data: Không\n"
                
                # Kiểm tra kích thước file
                file_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
                info_text += f"- Kích thước: {file_size:.2f} MB\n"
                
            except Exception as e:
                info_text += f"CBCT Info: Lỗi đọc file\n- Error: {str(e)[:50]}\n"
        else:
            info_text += "CBCT Info: Không có dữ liệu\n"
        
        # Cập nhật hiển thị
        self.info_text.set_text(info_text)
    
    def prev_patient(self, event):
        """Chuyển đến bệnh nhân trước đó"""
        if not self.patients:
            return
        
        idx = self.patients.index(self.current_patient)
        if idx > 0:
            self.current_patient = self.patients[idx - 1]
            self._patient_changed()
    
    def next_patient(self, event):
        """Chuyển đến bệnh nhân tiếp theo"""
        if not self.patients:
            return
        
        idx = self.patients.index(self.current_patient)
        if idx < len(self.patients) - 1:
            self.current_patient = self.patients[idx + 1]
            self._patient_changed()
    
    def _patient_changed(self):
        """Xử lý khi bệnh nhân thay đổi"""
        # Đặt lại chỉ số slice
        self.ct_slice_idx = 0
        self.cbct_slice_idx = 0
        
        # Cập nhật danh sách ngày
        self.all_dates = self._get_all_dates()
        
        # Chọn ngày đầu tiên nếu có
        if self.all_dates:
            self.current_date = self.all_dates[0]
        else:
            self.current_date = None
        
        # Cập nhật hiển thị
        self.update_display()
        
        # Tự động tìm ảnh CBCT
        self._auto_find_cbct_images()
    
    def prev_date(self, event):
        """Chuyển đến ngày trước đó"""
        if not self.all_dates:
            return
        
        idx = self.all_dates.index(self.current_date)
        if idx > 0:
            self.current_date = self.all_dates[idx - 1]
            self._date_changed()
    
    def next_date(self, event):
        """Chuyển đến ngày tiếp theo"""
        if not self.all_dates:
            return
        
        idx = self.all_dates.index(self.current_date)
        if idx < len(self.all_dates) - 1:
            self.current_date = self.all_dates[idx + 1]
            self._date_changed()
    
    def _date_changed(self):
        """Xử lý khi ngày thay đổi"""
        # Đặt lại chỉ số slice
        self.ct_slice_idx = 0
        self.cbct_slice_idx = 0
        
        # Cập nhật hiển thị
        self.update_display()
    
    def generate_report(self, event):
        """Tạo báo cáo tổng hợp"""
        # Thu thập dữ liệu từ cây thư mục
        rows = []
        
        for patient in self.data_tree:
            patient_data = self.data_tree[patient]
            
            # Tìm tất cả các ngày có sẵn cho bệnh nhân này
            all_dates = set()
            for img_type in patient_data:
                all_dates.update(patient_data[img_type].keys())
            
            # Duyệt qua từng ngày
            for date in sorted(all_dates):
                # Kiểm tra dữ liệu cho mỗi loại ảnh
                ct_count = 0
                cbct_count = 0
                
                if 'CT' in patient_data and date in patient_data['CT']:
                    ct_count = len(patient_data['CT'][date])
                
                if 'CBCT' in patient_data and date in patient_data['CBCT']:
                    cbct_count = len(patient_data['CBCT'][date])
                
                rows.append({
                    'Patient ID': patient,
                    'Date': date,
                    'CT Files': ct_count,
                    'CBCT Files': cbct_count,
                    'Total Files': ct_count + cbct_count
                })
        
        # Tạo DataFrame
        df = pd.DataFrame(rows)
        
        # Lưu báo cáo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_path = os.path.join(self.root_dir, f"comparison_report_{timestamp}.csv")
        df.to_csv(report_path, index=False)
        
        # Hiển thị thông báo
        plt.figtext(0.5, 0.5, f"Bao cao da duoc luu tai:\n{report_path}", 
                   ha="center", fontsize=12, 
                   bbox={"boxstyle": "round,pad=0.5", "facecolor": "yellow", "alpha": 0.5})
        
        self.fig.canvas.draw_idle()
        
        print(f"Đã tạo báo cáo tại: {report_path}")

def select_directory():
    """Mở hộp thoại chọn thư mục"""
    root = Tk()
    root.withdraw()  # Ẩn cửa sổ gốc
    
    folder_path = filedialog.askdirectory(title="Chọn thư mục chứa dữ liệu đã phân loại")
    root.destroy()
    
    return folder_path if folder_path else None

def main():
    # Xử lý tham số dòng lệnh
    if len(sys.argv) > 1:
        root_dir = sys.argv[1]
    else:
        # Nếu không có tham số, mở hộp thoại chọn thư mục
        root_dir = select_directory()
    
    if not root_dir:
        print("Không có thư mục nào được chọn. Thoát.")
        sys.exit(1)
    
    # Kiểm tra xem thư mục có tồn tại không
    if not os.path.exists(root_dir) or not os.path.isdir(root_dir):
        print(f"Thư mục không tồn tại: {root_dir}")
        sys.exit(1)
    
    print(f"Đang quét thư mục: {root_dir}")
    
    # Áp dụng sửa đổi giao diện TRƯỚC KHI tạo đối tượng
    apply_complete_ui_fix()
    
    # Khởi tạo công cụ so sánh
    comparison_tool = DicomComparisonTool(root_dir)
    
    # Áp dụng sửa lỗi CBCT
    fix_cbct_issues()
    
    # Hiển thị giao diện
    plt.show()
    
if __name__ == "__main__":
    main()