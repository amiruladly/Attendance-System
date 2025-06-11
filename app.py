# Fixed version of your Streamlit face attendance system with proper session_state handling
# and persistent class folder management

import streamlit as st
import face_recognition
import pandas as pd
import pickle
import io
import datetime
import gspread
import plotly.express as px
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os
import seaborn as sns
import matplotlib.pyplot as plt
import plotly.express as px
from matplotlib.colors import ListedColormap
from io import BytesIO
import base64

# Get the port Railway gives you (defaults to 8501 locally)
port = int(os.environ.get("PORT", 8501))

# Set Streamlit server options
os.environ["STREAMLIT_SERVER_PORT"] = str(port)
os.environ["STREAMLIT_SERVER_ADDRESS"] = "0.0.0.0"

# === Setup ===
CLASS_FOLDERS_FILE = "class_folders.pkl"
DEFAULT_CLASS_LIST = [
    "BVI3114 TECHNOLOGY SYSTEM OPTIMIZATION II",
    "BVI3124 APPLICATION SYSTEM DEVELOPMENT II",
    "UHF1111 MANDARIN FOR BEGINNERS",
    "BVI2254 CAPSTONE TECHNOPRENEUR I",
    "BVI3215 SYSTEM INTEGRATION DESIGNING",
    "ULE1362 ENGLISH FOR VOCATIONAL PURPOSES"
]

# === Google Auth Setup ===
SCOPE = ["https://www.googleapis.com/auth/drive", "https://spreadsheets.google.com/feeds"]
creds = Credentials.from_service_account_file("drive_credentials.json", scopes=SCOPE)
client = gspread.authorize(creds)
spreadsheet_url = "https://docs.google.com/spreadsheets/d/1KCA9QkzY9YTa46Ebz0etWbutWyGSx0Wmrdlrk6vtdGM"
drive_service = build("drive", "v3", credentials=creds)
PARENT_FOLDER_ID = "1_nqo09S2_8pxS9mVvdwwXO1IfVGD1vn7"

# === Load known faces ===
try:
    with open("known_faces.pkl", "rb") as f:
        known_data = pickle.load(f)
        known_faces = known_data["encodings"]
        known_metadata = known_data["metadata"]
except FileNotFoundError:
    known_faces = []
    known_metadata = []

# === Load class folders into session_state ===
if "class_folders" not in st.session_state:
    if os.path.exists(CLASS_FOLDERS_FILE):
        with open(CLASS_FOLDERS_FILE, "rb") as f:
            st.session_state.class_folders = pickle.load(f)
    else:
        st.session_state.class_folders = {}

    for cls in DEFAULT_CLASS_LIST:
        if cls not in st.session_state.class_folders:
            folder_id = drive_service.files().create(
                body={
                    'name': cls,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [PARENT_FOLDER_ID]
                },
                fields='id'
            ).execute()["id"]
            st.session_state.class_folders[cls] = folder_id

    with open(CLASS_FOLDERS_FILE, "wb") as f:
        pickle.dump(st.session_state.class_folders, f)

# === Cached Google Sheets reader ===
@st.cache_data(ttl=30)
def get_class_data(class_name):
    try:
        worksheet = client.open_by_url(spreadsheet_url).worksheet(class_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()

# === Streamlit UI ===
st.title("🎓 Student Face Attendance System")
tab1, tab2, tab3, tab4 = st.tabs(["🧑‍🎓 Register Face", "📝 Submit Attendance", "📈 Student Performance", "🛠️ Admin Panel"])

# === Tab 1: Registration ===
with tab1:
    st.subheader("Register Your Face")
    with st.form("register_form"):
        reg_name = st.text_input("Full Name")
        reg_id = st.text_input("Student ID")
        reg_email = st.text_input("Email")
        reg_phone = st.text_input("Phone Number")
        reg_img = st.camera_input("Capture Your Face")
        reg_submit = st.form_submit_button("Register")

        if reg_submit:
            if not reg_name or not reg_id or not reg_email or not reg_phone:
                st.error("❗ Please fill in all fields.")
            elif not reg_img:
                st.error("❗ Please capture a face image.")
            elif "@" not in reg_email or "." not in reg_email:
                st.error("❗ Invalid email.")
            elif not reg_phone.isdigit() or len(reg_phone) < 10 or len(reg_phone) > 15:
                st.error("❗ Invalid phone number.")
            else:
                image = face_recognition.load_image_file(io.BytesIO(reg_img.getvalue()))
                encodings = face_recognition.face_encodings(image)
                if not encodings:
                    st.error("❌ No face detected.")
                else:
                    known_faces.append(encodings[0])
                    known_metadata.append({"name": reg_name, "student_id": reg_id, "email": reg_email, "phone": reg_phone})
                    with open("known_faces.pkl", "wb") as f:
                        pickle.dump({"encodings": known_faces, "metadata": known_metadata}, f)
                    st.success(f"✅ {reg_name} registered successfully!")

# === Tab 2: Attendance ===
with tab2:
    st.subheader("Submit Attendance")
    selected_class = st.selectbox("Select Class", list(st.session_state.class_folders.keys()))
    face_img = st.camera_input("Capture Your Face")

    if face_img:
        image = face_recognition.load_image_file(io.BytesIO(face_img.getvalue()))
        encodings = face_recognition.face_encodings(image)
        if not encodings:
            st.error("❌ No face detected.")
        elif not known_faces:
            st.error("⚠️ No registered faces found.")
        else:
            face_encoding = encodings[0]
            distances = face_recognition.face_distance(known_faces, face_encoding)
            min_distance = min(distances)
            best_match_index = distances.tolist().index(min_distance)
            if min_distance < 0.45:
                matched = known_metadata[best_match_index]
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                filename = f"{matched['name']}_{matched['student_id']}_{selected_class}_{timestamp.replace(':', '-')}.jpg"
                media = MediaIoBaseUpload(io.BytesIO(face_img.getvalue()), mimetype="image/jpeg")
                uploaded = drive_service.files().create(
                    body={"name": filename, "parents": [st.session_state.class_folders[selected_class]]},
                    media_body=media,
                    fields="id"
                ).execute()
                file_url = f"https://drive.google.com/file/d/{uploaded['id']}/view"

                try:
                    sheet = client.open_by_url(spreadsheet_url).worksheet(selected_class)
                except gspread.exceptions.WorksheetNotFound:
                    sheet = client.open_by_url(spreadsheet_url).add_worksheet(title=selected_class, rows="100", cols="20")
                    sheet.append_row(["Timestamp", "Name", "Student ID", "Email", "Phone", "Class", "Status", "Image URL"])

                sheet.append_row([
                    timestamp,
                    matched['name'],
                    matched['student_id'],
                    matched.get('email', ''),
                    matched.get('phone', ''),
                    selected_class,
                    "Present",
                    file_url
                ])
                st.success(f"✅ Attendance submitted for {matched['name']} ({matched['student_id']})")
            else:
                st.error("❌ Face not recognized.")

with tab3:
    st.subheader("📈 Student Performance Dashboard")

    selected_class = st.selectbox("Select Class", list(st.session_state.class_folders.keys()), key="performance_class")
    df = get_class_data(selected_class)

    if df.empty:
        st.warning("No attendance data available for this class.")
    else:
        students = df[['Student ID', 'Name']].drop_duplicates().sort_values('Name')
        student_selection = st.selectbox(
            "Select Student",
            students.apply(lambda row: f"{row['Name']} ({row['Student ID']})", axis=1),
            key="performance_student"
        )

        selected_id = student_selection.split('(')[-1].replace(')', '').strip()
        student_df = df[df['Student ID'] == selected_id].copy()
        student_df['Date'] = pd.to_datetime(student_df['Timestamp']).dt.date

        if student_df.empty:
            st.info("No attendance records for this student.")
        else:
            total_attended = student_df.shape[0]
            first_day = pd.to_datetime(df['Timestamp']).min().date()
            last_day = pd.to_datetime(df['Timestamp']).max().date()
            total_possible_days = pd.date_range(start=first_day, end=last_day).nunique()
            attendance_pct = round((total_attended / total_possible_days) * 100, 2)

            class_avg = df.groupby('Student ID').size().mean()
            class_attendance_rate = round((class_avg / total_possible_days) * 100, 2)

            st.markdown(f"### 🎓 {student_df.iloc[0]['Name']} ({selected_id})")
            st.metric("✅ Days Attended", total_attended)
            st.metric("📊 Attendance Rate", f"{attendance_pct}%", delta=f"{attendance_pct - class_attendance_rate:.2f}% vs class avg")
            st.metric("📅 Total Attendance Days", total_possible_days)

            if attendance_pct < 75:
                st.error("⚠️ Low attendance! Below 75%.")

            # Download CSV
            st.markdown("### 📥 Download Student Report")
            csv_buf = io.StringIO()
            student_df.to_csv(csv_buf, index=False)
            st.download_button(
                label="Download Attendance CSV",
                data=csv_buf.getvalue().encode('utf-8'),
                file_name=f"{selected_class}_{selected_id}_attendance.csv",
                mime="text/csv"
            )

with tab4:
    st.subheader("Admin Panel")
    admin_code = st.text_input("Enter Admin Code", type="password")
    
    if admin_code == "admin123":
        st.success("Access granted ✅")

        if "admin_log" not in st.session_state:
            st.session_state.admin_log = []

        # === Add New Class ===
        st.markdown("### ➕ Add New Class")
        new_class = st.text_input("Class Name")
        if st.button("Add Class"):
            if new_class.strip() == "":
                st.error("Class name cannot be empty.")
            elif new_class in st.session_state.class_folders:
                st.warning("Class already exists.")
            else:
                folder_id = drive_service.files().create(
                    body={
                        'name': new_class,
                        'mimeType': 'application/vnd.google-apps.folder',
                        'parents': [PARENT_FOLDER_ID]
                    },
                    fields='id'
                ).execute()['id']
                st.session_state.class_folders[new_class] = folder_id
                with open(CLASS_FOLDERS_FILE, "wb") as f:
                    pickle.dump(st.session_state.class_folders, f)
                st.session_state.admin_log.append(f"[{datetime.datetime.now()}] Added class '{new_class}'")
                st.success(f"Class '{new_class}' added.")

        # === Remove Class ===
        st.markdown("### ➖ Remove Class")
        if st.session_state.class_folders:
            class_to_remove = st.selectbox("Class to remove", list(st.session_state.class_folders.keys()))
            if st.button("Remove Class"):
                del st.session_state.class_folders[class_to_remove]
                with open(CLASS_FOLDERS_FILE, "wb") as f:
                    pickle.dump(st.session_state.class_folders, f)
                st.session_state.admin_log.append(f"[{datetime.datetime.now()}] Removed class '{class_to_remove}'")
                st.success(f"Class '{class_to_remove}' removed.")
        else:
            st.info("No classes available to remove.")

        # === Attendance Dashboard ===
        st.markdown("---")
        st.markdown("### 📊 Attendance Dashboard")
        selected = st.selectbox("Select class", list(st.session_state.class_folders.keys()))

        df = get_class_data(selected)
        if df.empty:
            st.info("No data yet.")
        else:
            start_date = st.date_input("Start Date", datetime.date.today() - datetime.timedelta(days=7))
            end_date = st.date_input("End Date", datetime.date.today())
            if start_date > end_date:
                st.warning("Start date must be before end date.")
            else:
                filtered_df = df[
                    (pd.to_datetime(df["Timestamp"]) >= pd.to_datetime(start_date)) &
                    (pd.to_datetime(df["Timestamp"]) <= pd.to_datetime(end_date))
                ]

                if filtered_df.empty:
                    st.warning("No data for selected range.")
                else:
                    counts = filtered_df.groupby(["Student ID", "Name"]).size().reset_index(name="Count")
                    avg_attendance = counts["Count"].mean()

                    st.markdown(f"**📈 Average attendance:** `{avg_attendance:.2f}` times")
                    low_attendance = counts[counts["Count"] < avg_attendance]
                    st.markdown("**🚨 Students Below Average**")
                    st.dataframe(low_attendance)

                    st.markdown("**🏆 Top 3 Attendees**")
                    st.dataframe(counts.sort_values("Count", ascending=False).head(3))

                    # 📊 Pie Chart
                    st.plotly_chart(px.pie(counts, names="Name", values="Count", title="Attendance Distribution"))
                    
        # === CSV Export ===
        st.markdown("---")
        st.markdown("### 📥 Download Attendance Data")
        download_class = st.selectbox("Class to download", list(st.session_state.class_folders.keys()), key="download_class")
        csv_start = st.date_input("Start Date", value=datetime.date.today() - datetime.timedelta(days=7), key="csv_start")
        csv_end = st.date_input("End Date", value=datetime.date.today(), key="csv_end")

        if st.button("Download CSV"):
            df = get_class_data(download_class)
            if df.empty:
                st.warning("No data for that class.")
            else:
                filtered_df = df[
                    (pd.to_datetime(df["Timestamp"]) >= pd.to_datetime(csv_start)) &
                    (pd.to_datetime(df["Timestamp"]) <= pd.to_datetime(csv_end))
                ]
                if filtered_df.empty:
                    st.warning("No data in selected range.")
                else:
                    csv_buffer = io.StringIO()
                    filtered_df.to_csv(csv_buffer, index=False)
                    st.download_button(
                        label=f"Download {download_class} data",
                        data=csv_buffer.getvalue().encode("utf-8"),
                        file_name=f"{download_class}_attendance_{csv_start}_to_{csv_end}.csv",
                        mime="text/csv"
                    )
                    st.session_state.admin_log.append(
                        f"[{datetime.datetime.now()}] Downloaded data for '{download_class}' ({csv_start} to {csv_end})"
                    )

    else:
        if admin_code:
            st.warning("Enter valid admin code.")


