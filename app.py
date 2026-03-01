import streamlit as st
from supabase import create_client, Client
from streamlit_js_eval import get_geolocation
from deepface import DeepFace
from geopy.distance import geodesic
import tempfile
import os
import pandas as pd

# 1. إعداد الاتصال بـ Supabase
try:
    URL = st.secrets["SUPABASE_URL"].strip()
    KEY = st.secrets["SUPABASE_KEY"].strip()
    supabase: Client = create_client(URL, KEY)
except Exception as e:
    st.error("⚠️ فشل في قراءة مفاتيح الاتصال. تأكد من إعداد Secrets.")
    st.stop()

def check_location(user_lat, user_lon, work_lat, work_lon):
    return geodesic((user_lat, user_lon), (work_lat, work_lon)).meters

st.set_page_config(page_title="نظام الحضور الذكي", layout="wide")
st.sidebar.title("القائمة 🛡️")
choice = st.sidebar.radio("انتقل إلى:", ["تسجيل الحضور (User)", "لوحة الإدارة (Admin)"])

# ----------------- صفحة الإدارة (Admin) -----------------
if choice == "لوحة الإدارة (Admin)":
    st.header("👨‍✈️ لوحة تحكم المسؤول")
    tab1, tab2 = st.tabs(["➕ تسجيل موظف جديد", "📊 تقارير الحضور"])
    
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
                st.error(f"❌ خطأ في الحفظ: {e}")

    with tab2:
        st.subheader("📊 سجلات الحضور الحالية")
        try:
            # طلب البيانات مع جلب الاسم والوقت بمرونة
            response = supabase.table("attendance_logs").select("*, employees(full_name)").execute()
            
            if response.data:
                data_list = []
                for entry in response.data:
                    emp_info = entry.get('employees')
                    full_name = emp_info.get('full_name', 'غير معروف') if emp_info else "بانتظار الربط"
                    
                    # البحث عن الوقت بأي مسمى متاح
                    time_val = entry.get('created_at') or entry.get('timestamp') or "لا يوجد وقت"
                    
                    data_list.append({
                        "اسم الموظف": full_name,
                        "الحالة": entry.get('status', 'Check-in'),
                        "الوقت": time_val
                    })
                
                df = pd.DataFrame(data_list)
                st.dataframe(df, use_container_width=True)
                
                csv = df.to_csv(index=False).encode('utf-8-sig')
                st.download_button(label="📥 تحميل التقرير CSV", data=csv, file_name='attendance.csv', mime='text/csv')
            else:
                st.info("لا توجد سجلات حالياً.")
        except Exception as e:
            st.error(f"حدث خطأ في عرض التقارير: {e}")

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
            st.success(f"أهلاً {user['full_name']}")
            live_img = st.camera_input("التقط صورة للتحقق")
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
                    st.error(f"📍 موقعك بعيد عن العمل ({int(dist)} متر).")
        else:
            st.error("📧 هذا الإيميل غير مسجل.")
