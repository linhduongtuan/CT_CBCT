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
```

```python
# Hay Để tiết kiệm không gian lưu trữ, bạn có thể sử dụng tùy chọn tạo liên kết (symbolic link):
python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra --link
```

```python
# Điều chỉnh số luồng xử lý song song để tăng tốc độ:
python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra --workers 8
```


### Cấu Trúc Thư Mục Sau Khi Phân Loại 
```bash
thư_mục_đã_tổ_chức/
├── 20138770/                      # ID bệnh nhân
│   ├── CT/                        # Chỉ chứa ảnh CT ngày đầu tiên
│   │   └── 2024-11-21/            # Ngày chụp ban đầu
│   │       └── CT.20138770.*.dcm
│   ├── CBCT/                      # Thư mục mới cho ảnh CBCT
│   │   ├── 2024-12-05/            # Ngày điều trị
│   │   │   └── CT.20138770.*.dcm
│   │   └── 2024-12-10/            # Ngày điều trị khác
│   │       └── CT.20138770.*.dcm
│   ├── RS/                        # Structure sets
│   ├── RI/                        # Các ảnh RT Image khác
│   ├── RT/                        # RT Plans
│   └── RD/                        # RT Dose
└── 25001565/                      # Bệnh nhân khác
    ├── CT/
    ├── CBCT/
    └── ...
```

---

## Kiểm tra và loại bỏ các files (có thể) trùng lặp trong các thư mục sau khi phân loại

```python
# Sử dụng phương pháp mới "advanced" (mặc định)
python duplicate_detection.py /thư/mục/đầu/ra 
# /thư/mục/đầu/ra là thư mục chạy ở bước truóc đó với script:
# `python organize_dicom_by_patient_date.py /đường/dẫn/đến/thư/mục/DICOM --output /thư/mục/đầu/ra --workers 8`

# Di chuyển các file trùng lặp vào thư mục riêng
python duplicate_detection.py /thư/mục/đầu/ra  --action move

```

#### Có thể kiểm tra lại 1 lần nữa thư mục vừa kiểm tra các files trùng lặp

```python
python duplicate_detection.py /thư/mục/đầu/ra 
```

### Lưu ý: dường như files trùng lặp chỉ xuất hiện trong các folder chứa ảnh CT, nên ta chỉ nên chạy đoạn code này (thay vì chạy script duplicate_detection.py)

```python
# Chỉ tạo báo cáo trùng lặp trong thư mục CT (không thay đổi file)
python duplicate_detection_ct_only.py /thư/mục/đầu/ra --action report

# Di chuyển các file trùng lặp trong CT (giữ lại file nhỏ nhất)
python duplicate_detection_ct_only.py /thư/mục/đầu/ra --action move

# Xóa các file trùng lặp trong CT (giữ lại file nhỏ nhất)
python duplicate_detection_ct_only.py /thư/mục/đầu/ra --action delete
```

---

### Kiểm tra lại việc sắp xếp lại cấu trúc folders ở trên

```python
python verify_dicom_organization.py /thư/mục/đầu/ra
# Or
uv run verify_dicom_organization.py /thư/mục/đầu/ra
```

### Kiểm tra lại việc tìm kiếm và gom dữ liệu CT và CBCT dựa trên sự khác biệt về dung lượng và độ phân giải của các files CT và CBCT

```python
python cross_validate_dicom_stats.py /đường/dẫn/đến/thư/mục/dữ/liệu

# Hay chạy
python cross_validate_dicom_stats_1.py /đường/dẫn/đến/thư/mục/dữ/liệu
```

---

### Tính Năng Chính

- Phân loại tự động dựa trên tên file và metadata
  
- Tổ chức theo ngày điều trị từ metadata của ảnh
  
- Báo cáo tổng hợp số lượng ảnh cho mỗi bệnh nhân
  
- Xử lý song song để tăng tốc độ với số lượng ảnh lớn
  
- Lựa chọn sao chép hoặc tạo liên kết để tiết kiệm không gian

**Lưu Ý:**

- Script sẽ bỏ qua các file không phải ảnh CT hoặc CBCT như RT Records, RT Structure...
  
- Nếu file không có thông tin ngày trong metadata, nó sẽ được đặt trong thư mục "unknown_date"
  
- Báo cáo CSV sẽ giúp bạn dễ dàng kiểm tra số lượng ảnh của mỗi bệnh nhân theo ngày

Cấu trúc thư mục này giúp bạn dễ dàng theo dõi tiến trình điều trị của từng bệnh nhân theo thời gian, và phân biệt rõ giữa ảnh CT lập kế hoạch và ảnh CBCT kiểm tra hàng ngày.
