# CT_CBCT

```python
python improved_classify_ct_images.py \
/Users/linh/Downloads/cumulative_imaging_dose_MV_CBCT/ \
--patient 25001565 \
--output /Users/linh/Downloads/cumulative_imaging_dose_MV_CBCT/correct_classified
```

```python
python dicom_viewer_with_gdcm.py \
/Users/linh/Downloads/cumulative_imaging_dose_MV_CBCT/correct_classification/25001565_ct_planning_files.txt \
/Users/linh/Downloads/cumulative_imaging_dose_MV_CBCT/correct_classification/25001565_cbct_files.txt
```


```python
python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra

# Hay Để tiết kiệm không gian lưu trữ, bạn có thể sử dụng tùy chọn tạo liên kết (symbolic link):
python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra --link

# Điều chỉnh số luồng xử lý song song để tăng tốc độ:
python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra --workers 8
```

### Cấu Trúc Thư Mục Sau Khi Phân Loại 
```markdown
/thư/mục/đầu/ra/
├── summary_report.csv                # Báo cáo tổng hợp số lượng file
├── 25001565                          # Thư mục bệnh nhân 1
│   ├── CT                            # Thư mục ảnh CT
│   │   ├── 2023-01-15                # Ngày chụp
│   │   │   ├── CT.25001565.Image1.dcm
│   │   │   ├── CT.25001565.Image2.dcm
│   │   │   └── ...
│   │   └── 2023-02-10
│   │       └── ...
│   └── CBCT                          # Thư mục ảnh CBCT
│       ├── 2023-01-20                # Ngày điều trị
│       │   ├── RI.25001565.MV_1.dcm
│       │   └── ...
│       ├── 2023-01-25
│       │   └── ...
│       └── ...
├── 25001566                          # Thư mục bệnh nhân 2
│   ├── CT
│   │   └── ...
│   └── CBCT
│       └── ...
└── ...
```

---

### Tính Năng Chính

- Phân loại tự động dựa trên tên file và metadata
  
- Tổ chức theo ngày điều trị từ metadata của ảnh
  
- Báo cáo tổng hợp số lượng ảnh cho mỗi bệnh nhân
  
- Xử lý song song để tăng tốc độ với số lượng ảnh lớn
  
- Lựa chọn sao chép hoặc tạo liên kết để tiết kiệm không gian

**Script này xử lý hiệu quả cả hai loại file chính:**

- CT.* - Ảnh CT lập kế hoạch điều trị
  
- RI.* - Ảnh CBCT kiểm tra vị trí

**Lưu Ý:**

- Script sẽ bỏ qua các file không phải ảnh CT hoặc CBCT như RT Records, RT Structure...
  
- Nếu file không có thông tin ngày trong metadata, nó sẽ được đặt trong thư mục "unknown_date"
  
- Báo cáo CSV sẽ giúp bạn dễ dàng kiểm tra số lượng ảnh của mỗi bệnh nhân theo ngày

Cấu trúc thư mục này giúp bạn dễ dàng theo dõi tiến trình điều trị của từng bệnh nhân theo thời gian, và phân biệt rõ giữa ảnh CT lập kế hoạch và ảnh CBCT kiểm tra hàng ngày.
