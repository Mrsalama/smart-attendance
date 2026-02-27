import streamlit as st
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
from deepface import DeepFace
from geopy.distance import geodesic
import tempfile
import os
import pandas as pd # مكتبة لمعالجة البيانات وتصديرها

# 1. إعداد الاتصال بـ Supabase
try:
    URL = st.secrets["SUPABASE_URL"].strip()
    KEY = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(URL, KEY)
except Exception as e:
    st.error("⚠️ فشل في قراءة المفاتيح.")
    st.stop()

def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

st.set_page_config(page_title="نظام الحضور الذكي", layout="wide") # جعل الصفحة عريضة لعرض الجداول
st.sidebar.title("نظام الحضور الذكي 🛡️")
choice = st.sidebar.radio("القائمة:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ لوحة تحكم المسؤول")
    
    tab1, tab2 = st.tabs(["➕ تسجيل موظف", "📊 تقارير الحضور"])
    
    with tab1:
        current_loc = get_geolocation()
        with st.form("admin_reg_form", clear_on_submit=True):
            name = st.text_input("الاسم الكامل")
            email = st.text_input("البريد الإلكتروني")
            password = st.text_input("كلمة المرور", type="password")
            uploaded_image = st.camera_input("التقط الصورة المرجعية")
            submitted = st.form_submit_button("حفظ الموظف")
            
        if submitted and name and email and uploaded_image and current_loc:
            try:
                email_clean = email.strip().lower()
                file_path = f"{email_clean}.jpg"
                supabase.storage.from_("employee_faces").upload(path=file_path, file=uploaded_image.getvalue(), file_options={"content-type": "image/jpeg", "upsert": "true"})
                img_url = supabase.storage.from_("employee_faces").get_public_url(file_path)
                
                emp_data = {
                    "full_name": str(name),
                    "email": str(email_clean),
                    "password": str(password),
                    "profile_pic_url": str(img_url),
                    "work_lat": float(current_loc['coords']['latitude']),
                    "work_lon": float(current_loc['coords']['longitude'])
                }
                supabase.table("employees").insert(emp_data).execute()
                st.success(f"✅ تم تسجيل الموظف {name} بنجاح!")
            except Exception as e:
                st.error(f"❌ خطأ: {e}")

    with tab2:
        st.subheader("سجلات الحضور الحالية")
        # جلب البيانات من Supabase مع ربط الجداول
        try:
            # نقوم بجلب سجلات الحضور ودمجها مع أسماء الموظفين
            response = supabase.table("attendance_logs").select("created_at, status, employees(full_name, email)").execute()
            if response.data:
                # تحويل البيانات إلى جدول DataFrame
                data_list = []
                for entry in response.data:
                    data_list.append({
                        "الاسم": entry['employees']['full_name'],
                        "الإيميل": entry['employees']['email'],
                        "الحالة": entry['status'],
                        "الوقت والتاريخ": entry['created_at']
                    })
                df = pd.DataFrame(data_list)
                st.dataframe(df, use_container_width=True)
                
                # زر التحميل لملف CSV
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(
                    label="📥 تحميل التقرير كـ Excel (CSV)",
                    data=csv,
                    file_name='attendance_report.csv',
                    mime='text/csv',
                )
            else:
                st.info("لا توجد سجلات حضور حتى الآن.")
        except Exception as e:
            st.error(f"تعذر جلب التقارير: {e}")

# ----------------- صفحة الموظف (User) -----------------
else:
    st.header("📱 بوابة تسجيل الحضور")
    user_loc = get_geolocation()
    
    with st.form("user_login"):
        email_in = st.text_input("أدخل بريدك الإلكتروني")
        login_btn = st.form_submit_button("بدء التحقق")
    
    if login_btn and email_in:
        res = supabase.table("employees").select("*").eq("email", email_in.strip().lower()).execute()
        if res.data:
            user = res.data[0]
            st.success(f"مرحباً {user['full_name']}")
            live_img = st.camera_input("صور وجهك للتحقق")
            
            if live_img and user_loc:
                dist = check_location(user_loc['coords']['latitude'], user_loc['coords']['longitude'], user['work_lat'], user['work_lon'])
                if dist <= 100:
                    with st.spinner("جاري مطابقة الوجه..."):
                        tfile = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
                        tfile.write(live_img.read())
                        try:
                            result = DeepFace.verify(tfile.name, user['profile_pic_url'], enforce_detection=False)
                            if result['verified']:
                                st.success("✅ تم التحقق بنجاح!")
                                supabase.table("attendance_logs").insert({"employee_id": user['id'], "status": "Check-in"}).execute()
                                st.balloons()
                            else:
                                st.error("❌ الوجه غير مطابق.")
                        finally:
                            os.remove(tfile.name)
                else:
                    st.error(f"📍 أنت بعيد عن العمل بمسافة {int(dist)} متر.")
        else:
            st.error("❌ البريد غير مسجل.")
