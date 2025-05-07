import os
import sys
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.widgets import Slider, Button, RadioButtons
from datetime import datetime

# Cấu hình để sử dụng GDCM cho giải nén DICOM
try:
    import gdcm
    import pydicom
    pydicom.config.use_GDCM = True
    print("Đã kích hoạt GDCM để hỗ trợ giải nén DICOM")
except ImportError:
    import pydicom
    print("CẢNH BÁO: Không tìm thấy GDCM. Một số file DICOM nén có thể không đọc được.")
    print("Để cài đặt: pip install gdcm")

def load_dicom_paths_from_txt(txt_file_path):
    """Đọc danh sách đường dẫn đến các file DICOM từ file txt"""
    with open(txt_file_path, 'r') as f:
        paths = [line.strip() for line in f.readlines()]
    return paths

def try_read_dicom(path, stop_before_pixels=False):
    """Thử đọc file DICOM với nhiều phương pháp"""
    try:
        # Phương pháp 1: Đọc thông thường
        dcm = pydicom.dcmread(path, force=True, stop_before_pixels=stop_before_pixels)
        return dcm, None
    except Exception as e1:
        try:
            # Phương pháp 2: Với GDCM (nếu có)
            if 'gdcm' in sys.modules:
                pydicom.config.use_GDCM = True
                dcm = pydicom.dcmread(path, force=True, stop_before_pixels=stop_before_pixels)
                return dcm, None
        except Exception as e2:
            # Ghi lại thông tin lỗi
            errors = f"Standard: {str(e1)}, GDCM: {str(e2) if 'gdcm' in sys.modules else 'Not installed'}"
            return None, errors

def extract_metadata(path):
    """Trích xuất chỉ metadata từ file DICOM"""
    dcm, error = try_read_dicom(path, stop_before_pixels=True)
    if dcm is None:
        print(f"Lỗi khi đọc metadata từ {path}: {error}")
        return None
    
    # Trích xuất thông tin quan trọng
    info = {}
    try: info['SOPInstanceUID'] = dcm.SOPInstanceUID
    except: info['SOPInstanceUID'] = 'Unknown'
    
    try: info['TransferSyntaxUID'] = dcm.file_meta.TransferSyntaxUID
    except: info['TransferSyntaxUID'] = 'Unknown'
    
    try: info['PatientID'] = dcm.PatientID
    except: info['PatientID'] = 'Unknown'
    
    try: info['StudyDate'] = dcm.StudyDate
    except: info['StudyDate'] = 'Unknown'
    
    try: info['SeriesDate'] = dcm.SeriesDate
    except: info['SeriesDate'] = 'Unknown'
    
    try: info['Modality'] = dcm.Modality
    except: info['Modality'] = 'Unknown'
    
    try: info['SeriesDescription'] = dcm.SeriesDescription
    except: info['SeriesDescription'] = 'Unknown'
    
    try: info['SliceLocation'] = dcm.SliceLocation
    except: 
        try: info['SliceLocation'] = dcm.ImagePositionPatient[2]
        except: info['SliceLocation'] = 'Unknown'
    
    try: info['InstanceNumber'] = dcm.InstanceNumber
    except: info['InstanceNumber'] = 'Unknown'
    
    try: info['Rows'] = dcm.Rows
    except: info['Rows'] = 0
    
    try: info['Columns'] = dcm.Columns
    except: info['Columns'] = 0
    
    # Lưu đường dẫn file
    info['FilePath'] = path
    
    return info

def scan_and_group_dicom_files(file_paths):
    """Quét các file DICOM và nhóm chúng theo series"""
    print(f"Đang quét metadata từ {len(file_paths)} file DICOM...")
    
    # Trích xuất metadata từ tất cả file
    all_metadata = []
    for i, path in enumerate(file_paths):
        if i % 100 == 0:
            print(f"Đã quét {i}/{len(file_paths)} file...")
        
        metadata = extract_metadata(path)
        if metadata:
            all_metadata.append(metadata)
    
    print(f"Đã quét thành công {len(all_metadata)}/{len(file_paths)} file")
    
    # Nhóm theo SeriesDescription
    series_groups = {}
    for meta in all_metadata:
        key = meta.get('SeriesDescription', 'Unknown')
        if key not in series_groups:
            series_groups[key] = []
        series_groups[key].append(meta)
    
    # Sắp xếp mỗi nhóm theo SliceLocation hoặc InstanceNumber nếu có thể
    for key in series_groups:
        try:
            series_groups[key] = sorted(series_groups[key], 
                                       key=lambda x: float(x['SliceLocation']) 
                                       if x['SliceLocation'] != 'Unknown' 
                                       else float(x['InstanceNumber']))
        except:
            try:
                series_groups[key] = sorted(series_groups[key], key=lambda x: float(x['InstanceNumber']))
            except:
                print(f"Không thể sắp xếp series '{key}'")
    
    # Phân tích để xác định CT lập kế hoạch và CBCT
    ct_planning_series = []
    cbct_series = []
    
    # Tìm series có số lượng lớn nhất - có thể là CT lập kế hoạch
    max_series_size = 0
    max_series_key = None
    
    for key, meta_list in series_groups.items():
        # Ghi lại các thống kê
        date = meta_list[0].get('StudyDate', 'Unknown')
        modality = meta_list[0].get('Modality', 'Unknown')
        print(f"Series: {key}, Số lượng ảnh: {len(meta_list)}, Ngày: {date}, Modality: {modality}")
        
        if len(meta_list) > max_series_size:
            max_series_size = len(meta_list)
            max_series_key = key
    
    print(f"\nSeries có số lượng ảnh lớn nhất: {max_series_key} ({max_series_size} ảnh)")
    
    # Yêu cầu người dùng xác nhận
    print("\nHãy chọn series CT lập kế hoạch và CBCT dựa trên thông tin trên:")
    ct_series_choice = input("Nhập tên series CT lập kế hoạch (để trống cho series lớn nhất): ").strip()
    cbct_series_choice = input("Nhập tên series CBCT: ").strip()
    
    # Sử dụng series lớn nhất nếu người dùng không chọn
    if not ct_series_choice:
        ct_series_choice = max_series_key
    
    # Trích xuất đường dẫn file
    ct_planning_paths = [meta['FilePath'] for meta in series_groups.get(ct_series_choice, [])]
    cbct_paths = [meta['FilePath'] for meta in series_groups.get(cbct_series_choice, [])]
    
    return ct_planning_paths, cbct_paths, series_groups

def try_load_pixel_data(path):
    """Thử tải dữ liệu pixel từ file DICOM với nhiều phương pháp"""
    dcm, error = try_read_dicom(path)
    if dcm is None:
        return None, error
    
    try:
        pixel_array = dcm.pixel_array
        return pixel_array, None
    except Exception as e:
        return None, str(e)

def normalize_pixel_array(pixel_array, window_center=40, window_width=400):
    """Chuẩn hóa giá trị pixel cho hiển thị"""
    if pixel_array is None:
        return np.ones((512, 512))  # Trả về ảnh trắng nếu không có dữ liệu
    
    # Thiết lập cửa sổ
    min_val = window_center - window_width/2
    max_val = window_center + window_width/2
    
    # Clip và chuẩn hóa giá trị pixel
    pixel_array = np.clip(pixel_array, min_val, max_val)
    normalized = (pixel_array - min_val) / (max_val - min_val)
    
    return normalized

class DicomViewer:
    def __init__(self, ct_paths, cbct_paths):
        """Khởi tạo trình xem DICOM với đường dẫn đến ảnh CT và CBCT"""
        self.ct_paths = ct_paths
        self.cbct_paths = cbct_paths
        
        print(f"Số lượng ảnh CT: {len(ct_paths)}")
        print(f"Số lượng ảnh CBCT: {len(cbct_paths)}")
        
        # Chỉ số hiện tại
        self.ct_idx = 0 if ct_paths else None
        self.cbct_idx = 0 if cbct_paths else None
        
        # Thiết lập cửa sổ
        self.window_center = 40    # Window center (mặc định cho mô mềm)
        self.window_width = 400    # Window width (mặc định cho mô mềm)
        
        # Khởi tạo bộ đệm ảnh
        self.ct_cache = {}  # {index: pixel_array}
        self.cbct_cache = {}
        
        # Tạo giao diện
        self.create_ui()
    
    def load_dicom_image(self, is_ct, idx):
        """Tải một ảnh DICOM từ đường dẫn, có sử dụng bộ đệm"""
        cache = self.ct_cache if is_ct else self.cbct_cache
        paths = self.ct_paths if is_ct else self.cbct_paths
        
        # Nếu đã có trong bộ đệm thì trả về
        if idx in cache:
            return cache[idx]
        
        # Không thì tải mới
        if idx < len(paths):
            pixel_array, error = try_load_pixel_data(paths[idx])
            if error:
                print(f"Lỗi khi tải {'CT' if is_ct else 'CBCT'} idx={idx}: {error}")
                pixel_array = None
            
            # Lưu vào bộ đệm
            cache[idx] = pixel_array
            return pixel_array
        
        return None
    
    def create_ui(self):
        """Tạo giao diện người dùng"""
        self.fig, self.axes = plt.subplots(1, 2, figsize=(15, 8))
        plt.subplots_adjust(bottom=0.25, top=0.9)
        
        # Tiêu đề
        self.fig.suptitle("So sánh ảnh CT lập kế hoạch và CBCT", fontsize=16)
        
        # Thiết lập trục ảnh
        self.axes[0].set_title("CT lập kế hoạch điều trị")
        self.axes[1].set_title("CBCT kiểm tra")
        
        # Vô hiệu hóa trục
        for ax in self.axes:
            ax.set_xticks([])
            ax.set_yticks([])
        
        # Hiển thị ảnh trắng ban đầu
        self.ct_img = self.axes[0].imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        self.cbct_img = self.axes[1].imshow(np.ones((512, 512)), cmap='gray', vmin=0, vmax=1)
        
        # Thêm thanh trượt cho CT
        ax_ct_slider = plt.axes([0.1, 0.1, 0.35, 0.03])
        ct_max = max(len(self.ct_paths) - 1, 1)
        self.ct_slider = Slider(ax_ct_slider, 'CT Slice', 0, ct_max, valinit=0, valstep=1)
        self.ct_slider.on_changed(self.update_ct_slice)
        
        # Thêm thanh trượt cho CBCT
        ax_cbct_slider = plt.axes([0.55, 0.1, 0.35, 0.03])
        cbct_max = max(len(self.cbct_paths) - 1, 1)
        self.cbct_slider = Slider(ax_cbct_slider, 'CBCT Slice', 0, cbct_max, valinit=0, valstep=1)
        self.cbct_slider.on_changed(self.update_cbct_slice)
        
        # Thêm thanh trượt cho window center (độ sáng)
        ax_wc_slider = plt.axes([0.1, 0.05, 0.35, 0.03])
        self.wc_slider = Slider(ax_wc_slider, 'Window Center', -1000, 1000, valinit=self.window_center)
        self.wc_slider.on_changed(self.update_window)
        
        # Thêm thanh trượt cho window width (độ tương phản)
        ax_ww_slider = plt.axes([0.55, 0.05, 0.35, 0.03])
        self.ww_slider = Slider(ax_ww_slider, 'Window Width', 1, 2000, valinit=self.window_width)
        self.ww_slider.on_changed(self.update_window)
        
        # Thêm nút đồng bộ
        ax_sync = plt.axes([0.1, 0.01, 0.1, 0.03])
        self.sync_button = Button(ax_sync, 'Đồng bộ')
        self.sync_button.on_clicked(self.sync_slices)
        
        # Thêm nút lưu ảnh
        ax_save = plt.axes([0.25, 0.01, 0.1, 0.03])
        self.save_button = Button(ax_save, 'Lưu ảnh')
        self.save_button.on_clicked(self.save_current_view)
        
        # Thêm nút preset cửa sổ
        ax_presets = plt.axes([0.4, 0.01, 0.3, 0.03])
        self.presets = RadioButtons(ax_presets, ('Mô mềm', 'Phổi', 'Xương', 'Não'), active=0)
        self.presets.on_clicked(self.use_preset)
        
        # Thông tin ảnh
        self.ct_info_text = self.fig.text(0.1, 0.92, "", fontsize=9)
        self.cbct_info_text = self.fig.text(0.55, 0.92, "", fontsize=9)
        
        # Thông tin window
        self.window_info_text = self.fig.text(0.45, 0.15, "", fontsize=9, 
                                            horizontalalignment='center')
        self.update_window_info()
        
        # Cập nhật ban đầu
        self.update_ct_slice(0)
        self.update_cbct_slice(0)
    
    def update_ct_slice(self, val):
        """Cập nhật hiển thị CT khi thanh trượt thay đổi"""
        if not self.ct_paths:
            return
        
        idx = int(val)
        if idx >= len(self.ct_paths):
            idx = len(self.ct_paths) - 1
        
        self.ct_idx = idx
        
        # Tải ảnh từ bộ đệm hoặc từ file
        pixel_array = self.load_dicom_image(True, idx)
        
        # Chuẩn hóa và hiển thị
        normalized = normalize_pixel_array(pixel_array, self.window_center, self.window_width)
        self.ct_img.set_data(normalized)
        
        # Cập nhật thông tin
        if idx < len(self.ct_paths):
            info = f"CT slice: {idx+1}/{len(self.ct_paths)}\n"
            info += f"File: {os.path.basename(self.ct_paths[idx])}"
            self.ct_info_text.set_text(info)
        
        self.fig.canvas.draw_idle()
    
    def update_cbct_slice(self, val):
        """Cập nhật hiển thị CBCT khi thanh trượt thay đổi"""
        if not self.cbct_paths:
            return
        
        idx = int(val)
        if idx >= len(self.cbct_paths):
            idx = len(self.cbct_paths) - 1
        
        self.cbct_idx = idx
        
        # Tải ảnh từ bộ đệm hoặc từ file
        pixel_array = self.load_dicom_image(False, idx)
        
        # Chuẩn hóa và hiển thị
        normalized = normalize_pixel_array(pixel_array, self.window_center, self.window_width)
        self.cbct_img.set_data(normalized)
        
        # Cập nhật thông tin
        if idx < len(self.cbct_paths):
            info = f"CBCT slice: {idx+1}/{len(self.cbct_paths)}\n"
            info += f"File: {os.path.basename(self.cbct_paths[idx])}"
            self.cbct_info_text.set_text(info)
        
        self.fig.canvas.draw_idle()
    
    def update_window(self, val):
        """Cập nhật cửa sổ hiển thị"""
        self.window_center = self.wc_slider.val
        self.window_width = self.ww_slider.val
        
        self.update_ct_slice(self.ct_idx or 0)
        self.update_cbct_slice(self.cbct_idx or 0)
        self.update_window_info()
    
    def update_window_info(self):
        """Cập nhật thông tin về cửa sổ hiển thị"""
        info = f"Window: Center={int(self.window_center)}, Width={int(self.window_width)}"
        self.window_info_text.set_text(info)
        self.fig.canvas.draw_idle()
    
    def use_preset(self, label):
        """Sử dụng preset cửa sổ"""
        if label == 'Mô mềm':
            self.window_center = 40
            self.window_width = 400
        elif label == 'Phổi':
            self.window_center = -600
            self.window_width = 1500
        elif label == 'Xương':
            self.window_center = 400
            self.window_width = 1800
        elif label == 'Não':
            self.window_center = 40
            self.window_width = 80
        
        self.wc_slider.set_val(self.window_center)
        self.ww_slider.set_val(self.window_width)
        self.update_window(None)
    
    def sync_slices(self, event):
        """Đồng bộ vị trí tương đối giữa CT và CBCT"""
        if not self.ct_paths or not self.cbct_paths:
            return
        
        ct_ratio = self.ct_idx / (len(self.ct_paths) - 1) if len(self.ct_paths) > 1 else 0
        cbct_idx = int(ct_ratio * (len(self.cbct_paths) - 1))
        
        self.cbct_slider.set_val(cbct_idx)
        self.update_cbct_slice(cbct_idx)
    
    def save_current_view(self, event):
        """Lưu ảnh hiện tại"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comparison_{timestamp}.png"
        self.fig.savefig(filename, dpi=300, bbox_inches='tight')
        print(f"Đã lưu ảnh tại: {filename}")

def explore_dicom_directory(directory_path):
    """Khám phá thư mục DICOM và tìm tất cả các file .dcm"""
    dicom_files = []
    for root, _, files in os.walk(directory_path):
        for file in files:
            if file.lower().endswith('.dcm'):
                dicom_files.append(os.path.join(root, file))
    return dicom_files

def main():
    if len(sys.argv) not in [2, 3]:
        print("Sử dụng cách 1 (từ thư mục): python dicom_viewer_with_gdcm.py <thư_mục_chứa_dicom>")
        print("Sử dụng cách 2 (từ file txt): python dicom_viewer_with_gdcm.py <ct_planning_txt> <cbct_txt>")
        sys.exit(1)
    
    # Phương pháp 1: Từ thư mục
    if len(sys.argv) == 2 and os.path.isdir(sys.argv[1]):
        print(f"Khám phá thư mục DICOM: {sys.argv[1]}")
        all_dicom_files = explore_dicom_directory(sys.argv[1])
        print(f"Đã tìm thấy {len(all_dicom_files)} file DICOM")
        
        # Quét và nhóm các file
        ct_planning_paths, cbct_paths, _ = scan_and_group_dicom_files(all_dicom_files)
    
    # Phương pháp 2: Từ file txt
    elif len(sys.argv) == 3:
        ct_planning_txt = sys.argv[1]
        cbct_txt = sys.argv[2]
        
        if not os.path.exists(ct_planning_txt) or not os.path.exists(cbct_txt):
            print(f"Không tìm thấy file txt")
            sys.exit(1)
        
        ct_planning_paths = load_dicom_paths_from_txt(ct_planning_txt)
        cbct_paths = load_dicom_paths_from_txt(cbct_txt)
        print(f"Đã tìm thấy {len(ct_planning_paths)} đường dẫn CT và {len(cbct_paths)} đường dẫn CBCT")
    
    else:
        print("Tham số không hợp lệ")
        sys.exit(1)
    
    # Tạo và hiển thị trình xem
    viewer = DicomViewer(ct_planning_paths, cbct_paths)
    plt.show()

if __name__ == "__main__":
    main()