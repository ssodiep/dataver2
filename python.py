# project_valuation_app.py

import streamlit as st
import pandas as pd
import numpy_financial as npf # Thư viện chuyên dùng cho tính toán tài chính
from google import genai
from google.genai.errors import APIError
from docx import Document # Thư viện để đọc file Word (.docx)

# --- Cấu hình Trang Streamlit ---
st.set_page_config(
    page_title="App Đánh giá Phương án Kinh doanh",
    layout="wide"
)

st.title("Ứng dụng Đánh giá Phương án Kinh doanh 📈")
st.markdown("Sử dụng AI để trích xuất dữ liệu, tính toán hiệu quả dự án (NPV, IRR, PP, DPP) và nhận phân tích chuyên sâu.")

# --- Thiết lập Kết nối API (Bắt buộc phải cấu hình GEMINI_API_KEY trong Streamlit Secrets) ---
try:
    API_KEY = st.secrets["GEMINI_API_KEY"]
    CLIENT = genai.Client(api_key=API_KEY)
except KeyError:
    st.error("Lỗi: Không tìm thấy Khóa API 'GEMINI_API_KEY'. Vui lòng cấu hình Khóa API trong Streamlit Secrets.")
    st.stop()
except Exception as e:
    st.error(f"Lỗi khởi tạo Gemini Client: {e}")
    st.stop()


# --- CHỨC NĂNG 1: LỌC THÔNG TIN DỰ ÁN BẰNG AI ---

@st.cache_data(show_spinner="AI đang đọc và trích xuất thông tin tài chính...")
def extract_data_with_ai(file_content_text):
    """Sử dụng Gemini để trích xuất các thông số tài chính từ nội dung văn bản."""
    
    # Định dạng yêu cầu trích xuất
    required_info = [
        "Vốn đầu tư ban đầu (Initial Investment - Vốn tại năm 0)",
        "Dòng đời dự án (Project Life - Số năm)",
        "Doanh thu thuần hàng năm (Annual Revenue)",
        "Chi phí hoạt động hàng năm (Annual Operating Cost)",
        "WACC (Weighted Average Cost of Capital - Tỷ lệ chiết khấu)",
        "Thuế suất (Tax Rate)",
    ]
    
    # Prompt chi tiết cho Gemini
    prompt = f"""
    Bạn là một trợ lý tài chính chuyên nghiệp. Nhiệm vụ của bạn là đọc bản đề xuất kinh doanh dưới đây (được trích xuất từ file Word) và trích xuất các thông số tài chính quan trọng.
    
    QUAN TRỌNG: Hãy chỉ trả về **DUY NHẤT** một đối tượng JSON. Đối tượng này phải có các key chính xác sau, cùng với giá trị tương ứng được tìm thấy. Nếu không tìm thấy, hãy điền giá trị 0 (đối với số) hoặc 0.0 (đối với tỷ lệ) hoặc 'N/A' (đối với dòng đời).
    
    Key và mô tả dữ liệu cần trích xuất:
    1. initial_investment (Số tiền): Vốn đầu tư ban đầu (tại Năm 0).
    2. project_life (Số năm - Integer): Số năm hoạt động của dự án.
    3. annual_revenue (Số tiền): Doanh thu thuần ước tính hàng năm.
    4. annual_op_cost (Số tiền): Chi phí hoạt động hàng năm (không bao gồm khấu hao).
    5. wacc (Tỷ lệ - Ví dụ: 0.1 cho 10%): WACC (Tỷ lệ chiết khấu).
    6. tax_rate (Tỷ lệ - Ví dụ: 0.2 cho 20%): Thuế suất thuế thu nhập doanh nghiệp.
    
    NỘI DUNG ĐỀ XUẤT KINH DOANH:
    ---
    {file_content_text}
    ---
    """
    
    try:
        response = CLIENT.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config={"response_mime_type": "application/json"} # Yêu cầu đầu ra là JSON
        )
        
        # Parse JSON
        import json
        return json.loads(response.text)
    
    except APIError as e:
        st.error(f"Lỗi gọi Gemini API: {e}")
        return None
    except json.JSONDecodeError:
        st.error("AI không trả về đúng định dạng JSON. Vui lòng thử lại hoặc xem xét nội dung file.")
        return None
    except Exception as e:
        st.error(f"Lỗi không xác định khi trích xuất: {e}")
        return None

# Hàm đọc nội dung file .docx
def get_docx_text(file):
    """Đọc toàn bộ nội dung văn bản từ file .docx."""
    document = Document(file)
    return "\n".join([paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()])


# --- CHỨC NĂNG 2: XÂY DỰNG BẢNG DÒNG TIỀN DỰ ÁN ---

def create_cash_flow_table(data):
    """Tạo DataFrame dòng tiền dự án từ dữ liệu trích xuất."""
    
    # Chuyển đổi dữ liệu sang kiểu số và xử lý 'N/A'
    initial_investment = float(data.get('initial_investment', 0))
    project_life = int(data.get('project_life', 0))
    annual_revenue = float(data.get('annual_revenue', 0))
    annual_op_cost = float(data.get('annual_op_cost', 0))
    tax_rate = float(data.get('tax_rate', 0.2))
    
    if project_life <= 0:
        st.warning("Dòng đời dự án phải lớn hơn 0 để xây dựng bảng dòng tiền.")
        return None, None
        
    years = list(range(project_life + 1))
    
    # Giả định đơn giản: Không có khấu hao và Giá trị thanh lý = 0
    # Dòng tiền thuần hàng năm (CF) = (Doanh thu - Chi phí HĐ) * (1 - Thuế suất)
    
    # Khởi tạo DataFrame
    df = pd.DataFrame(index=[
        'Năm', 
        'Vốn đầu tư (CF0)', 
        'Doanh thu thuần', 
        'Chi phí HĐ', 
        'Lợi nhuận trước thuế',
        'Thuế TNDN', 
        'Lợi nhuận sau thuế', 
        'DÒNG TIỀN THUẦN (Net Cash Flow)'
    ])
    
    # Cột Năm 0
    df[0] = [
        0, 
        -initial_investment, # Dòng tiền âm
        0, 
        0, 
        0, 
        0, 
        0, 
        -initial_investment # Dòng tiền thuần năm 0
    ]
    
    # Các cột Năm 1 đến Năm N
    for year in range(1, project_life + 1):
        profit_before_tax = annual_revenue - annual_op_cost
        tax_amount = profit_before_tax * tax_rate
        profit_after_tax = profit_before_tax - tax_amount
        net_cash_flow = profit_after_tax # Vì giả định không có khấu hao, NCF = Lợi nhuận sau thuế
        
        df[year] = [
            year,
            0, # Không có vốn đầu tư sau năm 0
            annual_revenue,
            annual_op_cost,
            profit_before_tax,
            tax_amount,
            profit_after_tax,
            net_cash_flow
        ]
        
    df = df.transpose()
    df.set_index('Năm', inplace=True)
    df.index = df.index.astype(int) # Đảm bảo chỉ số Năm là Integer
    
    # Trả về DataFrame dòng tiền và mảng dòng tiền để tính toán
    cash_flows = df['DÒNG TIỀN THUẦN (Net Cash Flow)'].values
    
    return df, cash_flows


# --- CHỨC NĂNG 3: TÍNH TOÁN CÁC CHỈ SỐ HIỆU QUẢ DỰ ÁN ---

def calculate_project_metrics(cash_flows, wacc):
    """Tính toán NPV, IRR, PP, và DPP."""
    
    if wacc <= 0:
        st.warning("WACC phải lớn hơn 0 để tính NPV và DPP.")
        wacc = 1e-9 # Giá trị rất nhỏ để tránh lỗi, nhưng nên cảnh báo người dùng.
    
    # 1. NPV (Net Present Value)
    npv = npf.npv(wacc, cash_flows)
    
    # 2. IRR (Internal Rate of Return)
    try:
        irr = npf.irr(cash_flows)
    except:
        irr = float('nan')
        
    # 3. PP (Payback Period - Thời gian hoàn vốn) & 4. DPP (Discounted Payback Period - Hoàn vốn có chiết khấu)
    
    cumulative_cf = np.cumsum(cash_flows)
    discounted_cf = cash_flows / (1 + wacc) ** np.arange(len(cash_flows))
    cumulative_dcf = np.cumsum(discounted_cf)
    
    # Tính PP (Đơn giản hóa: Giả định CF đồng đều)
    initial_outlay = -cash_flows[0]
    pp_years = np.where(cumulative_cf >= 0)[0]
    pp = pp_years[0] if len(pp_years) > 0 else 'N/A'
    
    if isinstance(pp, np.int64) and pp > 0:
        # Tính toán chi tiết thời gian hoàn vốn (năm + tháng lẻ)
        pp_exact = pp - 1 + abs(cumulative_cf[pp - 1]) / cash_flows[pp]
        pp = pp_exact
    
    # Tính DPP (Đơn giản hóa: Giả định DCF đồng đều)
    dpp_years = np.where(cumulative_dcf >= 0)[0]
    dpp = dpp_years[0] if len(dpp_years) > 0 else 'N/A'
    
    if isinstance(dpp, np.int64) and dpp > 0:
        # Tính toán chi tiết thời gian hoàn vốn chiết khấu
        dpp_exact = dpp - 1 + abs(cumulative_dcf[dpp - 1]) / discounted_cf[dpp]
        dpp = dpp_exact
        
    return {
        "NPV": npv,
        "IRR": irr,
        "PP": pp,
        "DPP": dpp,
        "WACC": wacc
    }

# --- CHỨC NĂNG 4: YÊU CẦU AI PHÂN TÍCH ---

def get_analysis_from_ai(metrics_data):
    """Gửi các chỉ số đánh giá cho Gemini để nhận phân tích."""
    
    data_for_ai = pd.DataFrame(metrics_data.items(), columns=['Chỉ số', 'Giá trị']).to_markdown(index=False)
    
    prompt = f"""
    Bạn là một nhà tư vấn tài chính dày dạn kinh nghiệm. Dựa trên các chỉ số đánh giá dự án sau, hãy đưa ra nhận định tổng thể về tính khả thi và hiệu quả của dự án.
    
    Yêu cầu phân tích:
    1. Đánh giá tính **Khả thi** (dựa trên NPV và WACC/IRR).
    2. Đánh giá về **Rủi ro và Thanh khoản** (dựa trên PP và DPP).
    3. Đưa ra **Kết luận** và khuyến nghị ngắn gọn.
    
    Dữ liệu chỉ số:
    {data_for_ai}
    """
    
    try:
        response = CLIENT.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt
        )
        return response.text
    except APIError as e:
        return f"Lỗi gọi Gemini API khi phân tích: {e}"
    except Exception as e:
        return f"Lỗi không xác định: {e}"


# ================================== PHẦN CHÍNH CỦA ỨNG DỤNG ==================================

# --- Giao diện Tải File ---
uploaded_file = st.file_uploader(
    "1. Tải lên file **Word (.docx)** chứa Phương án Kinh doanh",
    type=['docx']
)

if uploaded_file is not None:
    
    # 1. Trích xuất nội dung file Word
    file_content = get_docx_text(uploaded_file)
    
    # Tạo nút bấm để thực hiện tác vụ lọc dữ liệu
    if st.button("🚀 Lọc Dữ liệu Dự án bằng AI"):
        
        # Gọi hàm AI để trích xuất
        with st.spinner('Đang phân tích tài liệu và trích xuất thông số...'):
            extracted_data = extract_data_with_ai(file_content)
        
        if extracted_data:
            st.session_state['extracted_data'] = extracted_data
            
            # Hiển thị dữ liệu đã trích xuất
            st.success("✅ Trích xuất dữ liệu thành công!")
            st.subheader("2. Dữ liệu Tài chính đã Lọc")
            
            # Định dạng và hiển thị dữ liệu
            display_data = {
                "Vốn đầu tư (CF0)": f"{extracted_data.get('initial_investment', 0):,.0f}",
                "Dòng đời dự án (năm)": int(extracted_data.get('project_life', 0)),
                "Doanh thu/năm": f"{extracted_data.get('annual_revenue', 0):,.0f}",
                "Chi phí HĐ/năm": f"{extracted_data.get('annual_op_cost', 0):,.0f}",
                "WACC (Tỷ lệ chiết khấu)": f"{extracted_data.get('wacc', 0.0) * 100:.2f}%",
                "Thuế suất": f"{extracted_data.get('tax_rate', 0.0) * 100:.2f}%",
            }
            
            st.json(display_data)

# --- Xử lý sau khi Lọc Dữ liệu Thành công ---
if 'extracted_data' in st.session_state:
    data = st.session_state['extracted_data']
    
    try:
        # Chuyển đổi WACC sang float để tính toán
        wacc = float(data.get('wacc', 0.0))
        
        # 2. Xây dựng Bảng Dòng Tiền
        cash_flow_df, cash_flows = create_cash_flow_table(data)
        
        if cash_flow_df is not None:
            
            st.markdown("---")
            st.subheader("3. Bảng Dòng tiền Dự án (Cash Flow Table)")
            st.dataframe(cash_flow_df.style.format('{:,.0f}'), use_container_width=True)
            
            # 3. Tính toán các Chỉ số
            st.markdown("---")
            st.subheader("4. Các Chỉ số Đánh giá Hiệu quả Dự án")
            
            metrics = calculate_project_metrics(cash_flows, wacc)
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("NPV (Giá trị hiện tại ròng)", f"{metrics['NPV']:,.0f}")
            with col2:
                st.metric("IRR (Tỷ suất sinh lợi nội tại)", f"{metrics['IRR']*100:.2f}%")
            with col3:
                st.metric("PP (Thời gian hoàn vốn)", f"{metrics['PP']:.2f} năm" if isinstance(metrics['PP'], float) else metrics['PP'])
            with col4:
                st.metric("DPP (Hoàn vốn có chiết khấu)", f"{metrics['DPP']:.2f} năm" if isinstance(metrics['DPP'], float) else metrics['DPP'])
                
            # 4. Phân tích AI
            st.markdown("---")
            st.subheader("5. Phân tích Hiệu quả Dự án (AI) 🤖")
            
            if st.button("💬 Yêu cầu AI Phân tích Chỉ số"):
                with st.spinner('Đang gửi chỉ số và chờ Gemini phân tích...'):
                    ai_analysis = get_analysis_from_ai(metrics)
                st.info(ai_analysis)
                
    except ValueError as ve:
        st.error(f"Lỗi: Không thể chuyển đổi dữ liệu thành kiểu số. Vui lòng kiểm tra dữ liệu trích xuất. Chi tiết: {ve}")
    except Exception as e:
        st.error(f"Lỗi không xác định trong quá trình tính toán: {e}")
