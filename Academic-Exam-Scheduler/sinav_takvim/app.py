
import sys, re, sqlite3
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QFormLayout, QHBoxLayout, QMessageBox,
    QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QSpinBox,
    QFileDialog, QDateEdit, QTimeEdit
)
from PySide6.QtGui import QAction
from PySide6.QtCore import Qt, QDate, QTime
from sqlalchemy.orm import Session

from core.db import SessionLocal, DB_PATH, Base, engine
from core.auth import verify, ensure_bootstrap_user
from core.models import (
    Classroom, Department, Student, Course, Enrollment, User, Exam
)


def _column_exists(conn, table, col):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return any(r[1] == col for r in cur.fetchall())

def _exams_has_unique_day_constraint(conn) -> bool:
    
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='exams'"
    ).fetchone()
    if not row or not row[0]:
        return False
    sql = row[0].upper().replace("\n", " ")
    
    return ("UNIQUE" in sql and "CLASSROOM_ID" in sql and "EXAM_DATE" in sql)

def _relax_exams_unique_constraint(conn):
    
    
    cols = conn.execute("PRAGMA table_info(exams)").fetchall()
    col_defs = []
    for cid, name, ctype, notnull, dflt, pk in cols:
        
        if name == "id":
            col_defs.append("id INTEGER PRIMARY KEY AUTOINCREMENT")
        else:
            
            typ = ctype or "TEXT"
            col_defs.append(f"{name} {typ}")



    
    create_sql = f"CREATE TABLE IF NOT EXISTS exams_new ({', '.join(col_defs)})"
    conn.execute("PRAGMA foreign_keys=OFF")
    conn.execute("BEGIN")
    try:
        conn.execute(create_sql)
        col_names = ", ".join([c[1] for c in cols])
        conn.execute(f"INSERT INTO exams_new ({col_names}) SELECT {col_names} FROM exams")
        conn.execute("DROP TABLE exams")
        conn.execute("ALTER TABLE exams_new RENAME TO exams")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys=ON")




def ensure_schema_and_seed():
    """Tabloları oluştur, eksik kolonları ekle, GÜN+SINIF uniq kısıtını kaldır,
    örnek bölümleri yükle."""
    Base.metadata.create_all(bind=engine)
    conn = sqlite3.connect(DB_PATH)
    try:
        

        try:
            if _exams_has_unique_day_constraint(conn):
                _relax_exams_unique_constraint(conn)
        except Exception as e:
            
            print("[WARN] exams UNIQUE constraint kaldırılamadı:", e)

       



        if not _column_exists(conn, "users", "name"):
            conn.execute("ALTER TABLE users ADD COLUMN name TEXT")
        if not _column_exists(conn, "users", "role"):
            conn.execute("ALTER TABLE users ADD COLUMN role TEXT")
        if not _column_exists(conn, "users", "department_id"):
            conn.execute("ALTER TABLE users ADD COLUMN department_id INTEGER")

        if not _column_exists(conn, "students", "class_year"):
            conn.execute("ALTER TABLE students ADD COLUMN class_year INTEGER")
        if not _column_exists(conn, "students", "department_id"):
            conn.execute("ALTER TABLE students ADD COLUMN department_id INTEGER")

        if not _column_exists(conn, "courses", "class_year"):
            conn.execute("ALTER TABLE courses ADD COLUMN class_year INTEGER")
        if not _column_exists(conn, "courses", "department_id"):
            conn.execute("ALTER TABLE courses ADD COLUMN department_id INTEGER")

        conn.commit()
    finally:
        conn.close()

    
    s = SessionLocal()
    try:
        if s.query(Department).count() == 0:
            s.add_all([
                Department(name="Bilgisayar Mühendisliği"),
                Department(name="Elektrik Mühendisliği"),
                Department(name="Elektronik Mühendisliği"),
                Department(name="Makine Mühendisliği"),
                Department(name="İnşaat Mühendisliği"),
            ])
            s.commit()
    finally:
        s.close()






def wipe_academic_data_for_department(parent, dept_id: int):
    """Seçili bölümün öğrenci, ders, enrollment ve sınavlarını siler. Derslikler korunur."""
    if QMessageBox.question(
        parent, "Onay",
        "Seçili BÖLÜM için tüm öğrenciler, dersler, kayıtlar ve sınavlar silinecek. Emin misiniz?",
        QMessageBox.Yes | QMessageBox.No
    ) != QMessageBox.Yes:
        return False
    s = SessionLocal()
    try:
        st_ids = [sid for (sid,) in s.query(Student.id).filter(Student.department_id == dept_id).all()]
        cr_ids = [cid for (cid,) in s.query(Course.id).filter(Course.department_id == dept_id).all()]

        if st_ids:
            s.query(Enrollment).filter(Enrollment.student_id.in_(st_ids)).delete(synchronize_session=False)
        if cr_ids:
            s.query(Enrollment).filter(Enrollment.course_id.in_(cr_ids)).delete(synchronize_session=False)


        s.query(Student).filter(Student.department_id == dept_id).delete(synchronize_session=False)
        s.query(Course).filter(Course.department_id == dept_id).delete(synchronize_session=False)
        s.query(Exam).filter(Exam.department_id == dept_id).delete(synchronize_session=False)


        s.commit()
        QMessageBox.information(parent, "Temizlendi", "Seçili bölüm için veriler temizlendi.")
        return True
    except Exception as e:
        s.rollback()
        QMessageBox.critical(parent, "Hata", f"Temizleme işlemi başarısız:\n{e}")
        return False
    finally:
        s.close()


class ClassroomWindow(QMainWindow):
    def __init__(self, parent=None, department_id: int | None = None):
        super().__init__(parent)
        self.current_dept_id = department_id
        self.setWindowTitle("Derslik Yönetimi")
        self.resize(960, 600)
        self.session: Session = SessionLocal()



        center = QWidget()
        root = QVBoxLayout(center)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)



        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight)
        self.deptLabel = QLabel(self._dept_name(self.current_dept_id))
        self.codeEdit = QLineEdit()
        self.nameEdit = QLineEdit()
        self.capSpin = QSpinBox(); self.capSpin.setRange(1, 5000)
        self.colSpin = QSpinBox(); self.colSpin.setRange(1, 50)
        self.rowSpin = QSpinBox(); self.rowSpin.setRange(1, 50)
        self.grpSpin = QSpinBox(); self.grpSpin.setRange(1, 10)



        form.addRow("Bölüm:", self.deptLabel)
        form.addRow("Derslik Kodu:", self.codeEdit)
        form.addRow("Derslik Adı:", self.nameEdit)
        form.addRow("Kapasite:", self.capSpin)
        form.addRow("Enine Sıra (Sütun):", self.colSpin)
        form.addRow("Boyuna Sıra (Satır):", self.rowSpin)
        form.addRow("Sıra Yapısı (Kişi):", self.grpSpin)

        root.addLayout(form)



        btns = QHBoxLayout()
        self.addBtn = QPushButton("Ekle")
        self.updateBtn = QPushButton("Güncelle")
        self.delBtn = QPushButton("Sil")
        self.clearBtn = QPushButton("Temizle")
        btns.addStretch(1)
        for b in (self.addBtn, self.updateBtn, self.delBtn, self.clearBtn):
            btns.addWidget(b)
        root.addLayout(btns)



        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Kod", "Ad", "Kapasite", "Sütun", "Satır", "Grup"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table)

        self.setCentralWidget(center)

        self.addBtn.clicked.connect(self.on_add)
        self.updateBtn.clicked.connect(self.on_update)
        self.delBtn.clicked.connect(self.on_delete)
        self.clearBtn.clicked.connect(self.clear_form)
        self.table.cellClicked.connect(self.on_row_click)

        self.load_table()

    def _dept_name(self, dept_id):
        s = SessionLocal()
        try:
            d = s.get(Department, dept_id)
            return d.name if d else ""
        finally:
            s.close()

    def clear_form(self):
        self.codeEdit.clear(); self.nameEdit.clear()
        self.capSpin.setValue(1); self.colSpin.setValue(1)
        self.rowSpin.setValue(1); self.grpSpin.setValue(1)
        if hasattr(self, "selected_id"): del self.selected_id

    def load_table(self):
        data = self.session.query(Classroom).filter(Classroom.department_id == self.current_dept_id).all()
        self.table.setRowCount(len(data))
        for row, c in enumerate(data):
            self.table.setItem(row, 0, QTableWidgetItem(str(c.code)))
            self.table.setItem(row, 1, QTableWidgetItem(c.name))
            self.table.setItem(row, 2, QTableWidgetItem(str(c.capacity)))
            self.table.setItem(row, 3, QTableWidgetItem(str(c.cols)))
            self.table.setItem(row, 4, QTableWidgetItem(str(c.rows)))
            item = QTableWidgetItem(str(c.desk_group)); item.setData(Qt.UserRole, c.id)
            self.table.setItem(row, 5, item)

    def on_add(self):
        code = self.codeEdit.text().strip()
        name = self.nameEdit.text().strip()
        cap = self.capSpin.value()
        cols = self.colSpin.value()
        rows = self.rowSpin.value()
        grp = self.grpSpin.value()
        if not code or not name:
            QMessageBox.warning(self, "Eksik Bilgi", "Derslik kodu ve adı zorunludur."); return
        if cols * rows * grp < cap:
            QMessageBox.warning(self, "Uyarı", "Kapasite, (satır*sütun*grup) değerinin üzerinde olamaz."); return
        if self.session.query(Classroom).filter_by(code=code).first():
            QMessageBox.warning(self, "Kayıt Var", f"{code} kodlu derslik zaten mevcut."); return
        c = Classroom(
            department_id=self.current_dept_id, code=code, name=name, capacity=cap,
            cols=cols, rows=rows, desk_group=grp
        )
        try:
            self.session.add(c); self.session.commit()
            QMessageBox.information(self, "Başarılı", f"{name} dersliği eklendi.")
            self.load_table(); self.clear_form()
        except Exception as e:
            self.session.rollback(); QMessageBox.critical(self, "Hata", f"Kayıt eklenemedi:\n{e}")

    def on_row_click(self, row, column):
        self.selected_id = self.table.item(row, 5).data(Qt.UserRole)
        self.codeEdit.setText(self.table.item(row, 0).text())
        self.nameEdit.setText(self.table.item(row, 1).text())
        self.capSpin.setValue(int(self.table.item(row, 2).text()))
        self.colSpin.setValue(int(self.table.item(row, 3).text()))
        self.rowSpin.setValue(int(self.table.item(row, 4).text()))
        self.grpSpin.setValue(int(self.table.item(row, 5).text()))


    def on_update(self):
        if not hasattr(self, "selected_id"):
            QMessageBox.warning(self, "Uyarı", "Güncellenecek derslik seçilmedi."); return
        c = self.session.get(Classroom, self.selected_id)
        if not c:
            QMessageBox.warning(self, "Uyarı", "Derslik bulunamadı."); return
        c.code = self.codeEdit.text().strip()
        c.name = self.nameEdit.text().strip()
        c.capacity = self.capSpin.value()
        c.cols = self.colSpin.value()
        c.rows = self.rowSpin.value()
        c.desk_group = self.grpSpin.value()
        try:
            self.session.commit(); QMessageBox.information(self, "Başarılı", "Derslik güncellendi.")
            self.load_table(); self.clear_form()
        except Exception as e:
            self.session.rollback(); QMessageBox.critical(self, "Hata", str(e))




    def on_delete(self):
        if not hasattr(self, "selected_id"):
            QMessageBox.warning(self, "Uyarı", "Silinecek derslik seçilmedi."); return
        if QMessageBox.question(self, "Emin misiniz?", "Bu dersliği silmek istiyor musunuz?",
                                QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
            return
        c = self.session.get(Classroom, self.selected_id)
        if c:
            try:
                self.session.delete(c); self.session.commit()
                QMessageBox.information(self, "Silindi", "Derslik silindi.")
                self.load_table(); self.clear_form()
            except Exception as e:
                self.session.rollback(); QMessageBox.critical(self, "Hata", str(e))



class StudentsWindow(QMainWindow):
    def __init__(self, parent=None, department_id: int | None = None):
        super().__init__(parent)
        self.current_dept_id = department_id
        self.setWindowTitle("Öğrenciler")
        self.resize(1100, 750)
        self.session: Session = SessionLocal()

        center = QWidget(); root = QVBoxLayout(center)
        top = QHBoxLayout()
        self.searchEdit = QLineEdit(); self.searchEdit.setPlaceholderText("Öğrenci no ile ara…")
        self.btnSearch = QPushButton("Ara"); self.btnReset = QPushButton("Sıfırla")
        self.btnWipe = QPushButton("(Bölüm) Veritabanını Temizle")
        top.addWidget(self.searchEdit); top.addWidget(self.btnSearch); top.addWidget(self.btnReset)
        top.addStretch(1); top.addWidget(self.btnWipe)
        root.addLayout(top)

        self.tblStudents = QTableWidget(); self.tblStudents.setColumnCount(3)
        self.tblStudents.setHorizontalHeaderLabels(["Numara", "Ad Soyad", "Sınıf"])
        self.tblStudents.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.tblStudents, 2)

        self.tblCourses = QTableWidget(); self.tblCourses.setColumnCount(4)
        self.tblCourses.setHorizontalHeaderLabels(["Ders Kodu", "Ders Adı", "Öğr. Gör.", "Sınıf"])
        self.tblCourses.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.tblCourses, 1)

        self.setCentralWidget(center)

        self.btnSearch.clicked.connect(self.apply_filter)
        self.btnReset.clicked.connect(self.load_students)
        self.btnWipe.clicked.connect(self.handle_wipe_clicked)
        self.tblStudents.cellClicked.connect(self.on_student_pick)

        self.load_students()

    def handle_wipe_clicked(self):
        if wipe_academic_data_for_department(self, self.current_dept_id):
            self.load_students(); self.tblCourses.setRowCount(0)
            if self.parent() and hasattr(self.parent(), "crs_win"):
                self.parent().crs_win.load_courses()

    def apply_filter(self):
        q = self.searchEdit.text().strip()
        if not q:
            self.load_students(); return
        data = (self.session.query(Student)
                .filter(Student.department_id == self.current_dept_id,
                        Student.number.ilike(f"%{q}%"))
                .order_by(Student.number).all())
        self.populate_students(data)

    def load_students(self):
        data = (self.session.query(Student)
                .filter(Student.department_id == self.current_dept_id)
                .order_by(Student.number).all())
        self.populate_students(data)

    def populate_students(self, data):
        self.tblStudents.setRowCount(len(data))
        for i, s in enumerate(data):
            num = QTableWidgetItem(s.number); num.setData(Qt.UserRole, s.id)
            self.tblStudents.setItem(i, 0, num)
            self.tblStudents.setItem(i, 1, QTableWidgetItem(s.name))
            self.tblStudents.setItem(i, 2, QTableWidgetItem(str(s.class_year) if s.class_year else ""))
        self.tblCourses.setRowCount(0)

    def on_student_pick(self, row, col):
        sid = self.tblStudents.item(row, 0).data(Qt.UserRole)
        s = self.session.get(Student, sid)
        if not s:
            return
        enrolls = (self.session.query(Course)
                   .join(Enrollment, Enrollment.course_id == Course.id)
                   .filter(Enrollment.student_id == s.id)
                   .order_by(Course.code).all())
        self.tblCourses.setRowCount(len(enrolls))
        for i, c in enumerate(enrolls):
            self.tblCourses.setItem(i, 0, QTableWidgetItem(c.code))
            self.tblCourses.setItem(i, 1, QTableWidgetItem(c.name))
            self.tblCourses.setItem(i, 2, QTableWidgetItem(c.instructor or ""))
            self.tblCourses.setItem(i, 3, QTableWidgetItem(str(c.class_year) if c.class_year else ""))



class CoursesWindow(QMainWindow):
    def __init__(self, parent=None, department_id: int | None = None):
        super().__init__(parent)
        self.current_dept_id = department_id
        self.setWindowTitle("Dersler")
        self.resize(1100, 750)
        self.session: Session = SessionLocal()

        center = QWidget(); root = QVBoxLayout(center)
        top = QHBoxLayout()
        self.btnWipe = QPushButton("(Bölüm) Veritabanını Temizle")
        top.addStretch(1); top.addWidget(self.btnWipe)
        root.addLayout(top)


        self.tblCourses = QTableWidget(); self.tblCourses.setColumnCount(4)
        self.tblCourses.setHorizontalHeaderLabels(["Ders Kodu", "Ders Adı", "Öğr. Gör.", "Sınıf"])
        self.tblCourses.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.tblCourses, 2)



        self.tblStudents = QTableWidget(); self.tblStudents.setColumnCount(3)
        self.tblStudents.setHorizontalHeaderLabels(["Numara", "Ad Soyad", "Sınıf"])
        self.tblStudents.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.tblStudents, 1)



        self.setCentralWidget(center)
        self.btnWipe.clicked.connect(self.handle_wipe_clicked)
        self.tblCourses.cellClicked.connect(self.on_course_pick)
        self.load_courses()



    def handle_wipe_clicked(self):
        if wipe_academic_data_for_department(self, self.current_dept_id):
            self.load_courses(); self.tblStudents.setRowCount(0)
            if self.parent() and hasattr(self.parent(), "stu_win"):
                self.parent().stu_win.load_students()

    def load_courses(self):
        data = (self.session.query(Course)
                .filter(Course.department_id == self.current_dept_id)
                .order_by(Course.class_year, Course.code).all())
        self.tblCourses.setRowCount(len(data))
        for i, c in enumerate(data):
            code = QTableWidgetItem(c.code); code.setData(Qt.UserRole, c.id)
            self.tblCourses.setItem(i, 0, code)
            self.tblCourses.setItem(i, 1, QTableWidgetItem(c.name))
            self.tblCourses.setItem(i, 2, QTableWidgetItem(c.instructor or ""))
            self.tblCourses.setItem(i, 3, QTableWidgetItem(str(c.class_year) if c.class_year else ""))
        self.tblStudents.setRowCount(0)

    def on_course_pick(self, row, col):
        cid = self.tblCourses.item(row, 0).data(Qt.UserRole)
        c = self.session.get(Course, cid)
        if not c:
            return
        stus = (self.session.query(Student)
                .join(Enrollment, Enrollment.student_id == Student.id)
                .filter(Enrollment.course_id == c.id)
                .order_by(Student.number).all())
        self.tblStudents.setRowCount(len(stus))
        for i, s in enumerate(stus):
            self.tblStudents.setItem(i, 0, QTableWidgetItem(s.number))
            self.tblStudents.setItem(i, 1, QTableWidgetItem(s.name))
            self.tblStudents.setItem(i, 2, QTableWidgetItem(str(s.class_year) if s.class_year else ""))



class CoordinatorsWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Koordinatörler")
        self.resize(900, 600)
        self.session: Session = SessionLocal()

        center = QWidget(); root = QVBoxLayout(center)
        form = QFormLayout()
        self.nameEdit = QLineEdit()
        self.emailEdit = QLineEdit()
        self.passEdit = QLineEdit(); self.passEdit.setEchoMode(QLineEdit.Password)
        self.deptCombo = QComboBox()
        for d in self.session.query(Department).order_by(Department.name).all():
            self.deptCombo.addItem(d.name, d.id)
        form.addRow("Ad Soyad:", self.nameEdit)
        form.addRow("E-posta:", self.emailEdit)
        form.addRow("Şifre:", self.passEdit)
        form.addRow("Bölüm:", self.deptCombo)

        btns = QHBoxLayout()
        self.btnAdd = QPushButton("Koordinatör Ekle")
        self.btnDel = QPushButton("Seçileni Sil")
        btns.addStretch(1); btns.addWidget(self.btnAdd); btns.addWidget(self.btnDel)

        self.tbl = QTableWidget(); self.tbl.setColumnCount(3)
        self.tbl.setHorizontalHeaderLabels(["Ad Soyad", "E-posta", "Bölüm"])
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)


        root.addLayout(form); root.addLayout(btns); root.addWidget(self.tbl)
        self.setCentralWidget(center)


        self.btnAdd.clicked.connect(self.on_add)
        self.btnDel.clicked.connect(self.on_delete)
        self.tbl.cellClicked.connect(self.on_pick)

        self.load_table()

    def load_table(self):
        data = (self.session.query(User)
                .filter((User.role == "coordinator"))
                .order_by(User.email).all())
        self.tbl.setRowCount(len(data))
        for i, u in enumerate(data):
            dep_name = self.session.get(Department, u.department_id).name if u.department_id else ""
            nm = QTableWidgetItem(u.name or ""); nm.setData(Qt.UserRole, u.id)
            self.tbl.setItem(i, 0, nm)
            self.tbl.setItem(i, 1, QTableWidgetItem(u.email))
            self.tbl.setItem(i, 2, QTableWidgetItem(dep_name))

    def on_pick(self, row, col):
        self.selected_id = self.tbl.item(row, 0).data(Qt.UserRole)

    def on_add(self):
        from core.auth import _hash_password
        name = self.nameEdit.text().strip()
        email = self.emailEdit.text().strip()
        pwd = self.passEdit.text()
        dept_id = self.deptCombo.currentData()
        if not email or not pwd or not dept_id:
            QMessageBox.warning(self, "Eksik", "E-posta, şifre ve bölüm zorunludur."); return
        if self.session.query(User).filter_by(email=email).first():
            QMessageBox.warning(self, "Var", "Bu e-posta zaten kayıtlı."); return
        try:
            self.session.add(User(
                name=name, email=email,
                password_hash=_hash_password(pwd),
                role="coordinator",
                department_id=dept_id
            ))
            self.session.commit()
            QMessageBox.information(self, "OK", "Koordinatör eklendi.")
            self.nameEdit.clear(); self.emailEdit.clear(); self.passEdit.clear()
            self.load_table()
        except Exception as e:
            self.session.rollback(); QMessageBox.critical(self, "Hata", str(e))

    def on_delete(self):
        if not hasattr(self, "selected_id"):
            QMessageBox.warning(self, "Uyarı", "Silinecek koordinatörü seçin."); return
        if QMessageBox.question(self, "Onay", "Seçili koordinatör silinsin mi?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        u = self.session.get(User, self.selected_id)
        if not u or (u.role or "").lower() != "coordinator":
            QMessageBox.warning(self, "Uyarı", "Seçili kayıt bulunamadı."); return
        try:
            self.session.delete(u); self.session.commit()
            QMessageBox.information(self, "Silindi", "Koordinatör silindi.")
            self.load_table()
        except Exception as e:
            self.session.rollback(); QMessageBox.critical(self, "Hata", str(e))




class ExamsWindow(QMainWindow):
    def __init__(self, parent=None, department_id: int | None = None):
        super().__init__(parent)
        self.current_dept_id = department_id
        self.setWindowTitle("Sınavlar")
        self.resize(1100, 750)
        self.session: Session = SessionLocal()



        center = QWidget(); root = QVBoxLayout(center)

        

        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight)



        self.roomCombo = QComboBox()
        for c in (self.session.query(Classroom)
                  .filter(Classroom.department_id == self.current_dept_id)
                  .order_by(Classroom.code).all()):
            self.roomCombo.addItem(f"{c.code} — {c.name}", c.id)

        self.courseCombo = QComboBox()
        for cr in (self.session.query(Course)
                   .filter(Course.department_id == self.current_dept_id)
                   .order_by(Course.code).all()):
            self.courseCombo.addItem(f"{cr.code} — {cr.name}", cr.id)

        self.dateEdit = QDateEdit(); self.dateEdit.setCalendarPopup(True); self.dateEdit.setDate(QDate.currentDate())
        self.startEdit = QTimeEdit(); self.startEdit.setDisplayFormat("HH:mm"); self.startEdit.setTime(QTime(9,0))
        self.endEdit = QTimeEdit(); self.endEdit.setDisplayFormat("HH:mm"); self.endEdit.setTime(QTime(11,0))

        form.addRow("Derslik:", self.roomCombo)
        form.addRow("Ders:", self.courseCombo)
        form.addRow("Tarih:", self.dateEdit)
        form.addRow("Başlangıç:", self.startEdit)
        form.addRow("Bitiş:", self.endEdit)
        root.addLayout(form)

        # buttons
        btns = QHBoxLayout()
        self.btnAdd = QPushButton("Sınav Ekle")
        self.btnDel = QPushButton("Seçileni Sil")
        self.btnClear = QPushButton("Temizle")
        self.btnPdf = QPushButton("PDF Dışa Aktar (Program)")
        btns.addStretch(1)
        for b in (self.btnAdd, self.btnDel, self.btnClear, self.btnPdf):
            btns.addWidget(b)
        root.addLayout(btns)

        # table
        self.table = QTableWidget()
        self.table.setColumnCount(6)
        self.table.setHorizontalHeaderLabels(["Tarih", "Saat", "Ders Kodu", "Ders Adı", "Derslik", "ID"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setColumnHidden(5, True)
        root.addWidget(self.table)

        self.setCentralWidget(center)

        # conns
        self.btnAdd.clicked.connect(self.on_add_exam)
        self.btnDel.clicked.connect(self.on_delete_exam)
        self.btnClear.clicked.connect(self.clear_form)
        self.btnPdf.clicked.connect(self.export_pdf)
        self.table.cellClicked.connect(self.on_row_pick)


        self.load_table()

    

    #timeIntersects
    def _tmin(self, hhmm: str) -> int:
        if not hhmm: return -1
        try:
            h, m = hhmm.split(":")
            return int(h) * 60 + int(m)
        except Exception:
            return -1


    
    def clear_form(self):
        self.roomCombo.setCurrentIndex(0 if self.roomCombo.count() else -1)
        self.courseCombo.setCurrentIndex(0 if self.courseCombo.count() else -1)
        self.dateEdit.setDate(QDate.currentDate())
        self.startEdit.setTime(QTime(9,0))
        self.endEdit.setTime(QTime(11,0))
        if hasattr(self, "selected_id"): del self.selected_id


    def load_table(self):
        exams = (self.session.query(Exam)
                 .filter(Exam.department_id == self.current_dept_id)
                 .order_by(Exam.exam_date, Exam.start_time).all())
        self.table.setRowCount(len(exams))
        for i, ex in enumerate(exams):
            course = self.session.get(Course, ex.course_id)
            room = self.session.get(Classroom, ex.classroom_id)
            self.table.setItem(i, 0, QTableWidgetItem(ex.exam_date))
            self.table.setItem(i, 1, QTableWidgetItem(f"{ex.start_time or ''}-{ex.end_time or ''}"))
            self.table.setItem(i, 2, QTableWidgetItem(course.code if course else ""))
            self.table.setItem(i, 3, QTableWidgetItem(course.name if course else ""))
            self.table.setItem(i, 4, QTableWidgetItem(room.code if room else ""))
            iditem = QTableWidgetItem(str(ex.id)); iditem.setData(Qt.UserRole, ex.id)
            self.table.setItem(i, 5, iditem)

    def on_row_pick(self, row, col):
        self.selected_id = self.table.item(row, 5).data(Qt.UserRole)

    def on_add_exam(self):
        if self.roomCombo.count() == 0 or self.courseCombo.count() == 0:
            QMessageBox.warning(self, "Eksik", "Bu bölüm için derslik veya ders bulunamadı."); return
        room_id = int(self.roomCombo.currentData())
        course_id = int(self.courseCombo.currentData())
        d = self.dateEdit.date().toString("yyyy-MM-dd")
        s = self.startEdit.time().toString("HH:mm")
        e = self.endEdit.time().toString("HH:mm")

        

        if self._tmin(s) >= self._tmin(e):
            QMessageBox.warning(self, "Uyarı", "Başlangıç saati bitişten küçük olmalı."); return

        

        same_day_rooms = (self.session.query(Exam)
                          .filter(Exam.department_id == self.current_dept_id,
                                  Exam.classroom_id == room_id,
                                  Exam.exam_date == d).all())
        new_start = self._tmin(s)
        new_end   = self._tmin(e)
        for ex in same_day_rooms:
            if not ex.start_time or not ex.end_time:
                QMessageBox.warning(self, "Uyarı", "Sınıf bu tarihte dolu."); return
            ex_start = self._tmin(ex.start_time)
            ex_end   = self._tmin(ex.end_time)
            
            if new_start < ex_end and ex_start < new_end:
                QMessageBox.warning(self, "Uyarı",
                                    f"Sınıf bu tarihte {ex.start_time}-{ex.end_time} arasında dolu.")
                return

        

        ex = Exam(
            department_id=self.current_dept_id,
            classroom_id=room_id, course_id=course_id,
            exam_date=d, start_time=s, end_time=e
        )
        try:
            self.session.add(ex); self.session.commit()
            self.load_table(); self.clear_form()
            QMessageBox.information(self, "Eklendi", "Sınav takvime eklendi.")
        except Exception as err:
            self.session.rollback()
            QMessageBox.critical(self, "Hata", f"Kayıt eklenemedi:\n{err}")

    def on_delete_exam(self):
        if not hasattr(self, "selected_id"):
            QMessageBox.warning(self, "Uyarı", "Silmek için listeden bir sınav seçin."); return
        ex = self.session.get(Exam, self.selected_id)
        if not ex:
            QMessageBox.warning(self, "Uyarı", "Kayıt bulunamadı."); return
        if QMessageBox.question(self, "Onay", "Seçili sınav silinsin mi?",
                                QMessageBox.Yes | QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.session.delete(ex); self.session.commit()
            self.load_table(); self.clear_form()
            QMessageBox.information(self, "Silindi", "Sınav silindi.")
        except Exception as err:
            self.session.rollback(); QMessageBox.critical(self, "Hata", f"Silinemedi:\n{err}")

    def export_pdf(self):
        
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        except Exception:
            QMessageBox.critical(self, "Eksik Paket",
                                 "PDF için 'reportlab' gerekiyor.\nKurulum:\n\npip install reportlab")
            return

        path, _ = QFileDialog.getSaveFileName(self, "PDF Kaydet", "sinav_programi.pdf", "PDF Files (*.pdf)")
        if not path:
            return

        exams = (self.session.query(Exam)
                 .filter(Exam.department_id == self.current_dept_id)
                 .order_by(Exam.exam_date, Exam.start_time).all())

        data = [["Tarih", "Saat", "Ders Kodu", "Ders Adı", "Derslik"]]
        for ex in exams:
            c = self.session.get(Course, ex.course_id)
            r = self.session.get(Classroom, ex.classroom_id)
            saat = f"{ex.start_time or ''}-{ex.end_time or ''}".strip("-")
            data.append([ex.exam_date, saat, c.code if c else "", c.name if c else "", r.code if r else ""])

        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        dept = self.session.get(Department, self.current_dept_id)
        story.append(Paragraph(f"<b>Sınav Programı — {dept.name if dept else ''}</b>", styles["Title"]))
        story.append(Spacer(1, 12))
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
            ("TEXTCOLOR", (0,0), (-1,0), colors.black),
            ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
            ("ALIGN", (0,0), (-1,-1), "CENTER"),
            ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
            ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.whitesmoke, colors.lightyellow]),
        ]))
        story.append(table)
        try:
            doc.build(story)
            QMessageBox.information(self, "PDF", "Sınav programı PDF olarak kaydedildi.")
        except Exception as e:
            QMessageBox.critical(self, "Hata", f"PDF oluşturulamadı:\n{e}")





class MainWindow(QMainWindow):
    def __init__(self, user, department_id: int, parent=None):
        super().__init__(parent)
        self.user = user
        self.current_dept_id = department_id
        s = SessionLocal()
        try:
            dept = s.get(Department, department_id)
            dept_name = dept.name if dept else ""
        finally:
            s.close()

        self.dept_name = dept_name
        self.setWindowTitle(f"Dinamik Sınav Takvimi — {user.email} — [{dept_name}]")
        self.resize(1200, 780)

        center = QWidget()
        v = QVBoxLayout(center)
        label = QLabel(f"Hoş geldiniz, {user.email} — Bölüm: {dept_name}")
        label.setAlignment(Qt.AlignCenter)
        v.addWidget(label)
        self.setCentralWidget(center)


        menubar = self.menuBar()

        

        m_admin = menubar.addMenu("Yönetim")
        act_classrooms = QAction("Derslikler…", self)
        act_classrooms.triggered.connect(self.open_classrooms)
        m_admin.addAction(act_classrooms)

        if (self.user.role or "").lower() == "admin":
            act_coords = QAction("Koordinatörler…", self)
            act_coords.triggered.connect(self.open_coordinators)
            m_admin.addAction(act_coords)

        


        m_view = menubar.addMenu("Görünüm")
        act_students = QAction("Öğrenciler…", self)
        act_students.triggered.connect(self.open_students)
        act_courses = QAction("Dersler…", self)
        act_courses.triggered.connect(self.open_courses)
        m_view.addAction(act_students)
        m_view.addAction(act_courses)

        
        m_data = menubar.addMenu("Veri")
        act_import_students = QAction("Öğrenci Excel Yükle…", self)
        act_import_courses = QAction("Ders Excel Yükle…", self)
        act_import_students.triggered.connect(self.import_students_excel)
        act_import_courses.triggered.connect(self.import_courses_excel)
        m_data.addAction(act_import_students)
        m_data.addAction(act_import_courses)

       
        m_exam = menubar.addMenu("Sınav")
        act_exams = QAction("Sınavlar…", self); act_exams.triggered.connect(self.open_exams)
        m_exam.addAction(act_exams)

        
        m_session = menubar.addMenu("Oturum")
        act_logout = QAction("Çıkış Yap", self)
        act_logout.triggered.connect(self.logout)
        m_session.addAction(act_logout)

    

    def open_classrooms(self):
        self.cls_win = ClassroomWindow(self, department_id=self.current_dept_id); self.cls_win.show()
    def open_students(self):
        self.stu_win = StudentsWindow(self, department_id=self.current_dept_id); self.stu_win.show()
    def open_courses(self):
        self.crs_win = CoursesWindow(self, department_id=self.current_dept_id); self.crs_win.show()
    def open_coordinators(self):
        self.coord_win = CoordinatorsWindow(self); self.coord_win.show()
    def open_exams(self):
        self.exam_win = ExamsWindow(self, department_id=self.current_dept_id); self.exam_win.show()

    
    def logout(self):
        if QMessageBox.question(
            self,
            "Çıkış Yap",
            f"{self.user.email} hesabından çıkmak istiyor musunuz?",
            QMessageBox.Yes | QMessageBox.No
        ) == QMessageBox.Yes:
            from app import LoginWindow  
            self.login_win = LoginWindow()
            self.login_win.show()
            self.close()

    

    def import_courses_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Dersler Excel Seç", "",
                                              "Excel Files (*.xlsx *.xls);;All Files (*)")
        if not path: return
        try:
            import pandas as pd
        except Exception:
            QMessageBox.critical(self, "Hata", "pandas yok. Kurulum:\npip install pandas openpyxl"); return




        QApplication.setOverrideCursor(Qt.WaitCursor); QApplication.processEvents()
        try:
            df = pd.read_excel(path, dtype=str)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", f"Excel okunamadı:\n{e}"); return
        QApplication.restoreOverrideCursor(); QApplication.processEvents()


        if df.shape[1] < 3:
            QMessageBox.warning(self, "Uyarı", "Excel'de en az 3 sütun bekleniyor (Kod, Ad, Öğr. Gör.)."); return

        col_code, col_name, col_inst = df.columns[0], df.columns[1], df.columns[2]

        def parse_year(s):
            if not isinstance(s, str): return None
            m = re.search(r"(\d+)\s*\.\s*s[ıi]n[ıi]f", s.lower())
            return int(m.group(1)) if m else None

        current_year = parse_year(col_code) or 1

        s = SessionLocal()
        added = updated = 0
        try:
            for _, row in df.iterrows():
                code_cell = row.get(col_code)
                name_cell = row.get(col_name)
                inst_cell = row.get(col_inst)

                code = (code_cell or "").strip() if isinstance(code_cell, str) else str(code_cell or "").strip()
                name = (name_cell or "").strip() if isinstance(name_cell, str) else ""
                inst = (inst_cell or "").strip() if isinstance(inst_cell, str) else ""

                year_marker = parse_year(code)
                if year_marker:
                    current_year = year_marker
                    continue

                
                if code.upper() == "DERS KODU" or code == "" or (isinstance(name, str) and name.upper().startswith("DERS")):
                    continue
                if not code or not name:
                    continue

                crs = s.query(Course).filter_by(code=code).first()
                if crs:
                    ch = False
                    if crs.name != name: crs.name = name; ch = True
                    if (crs.instructor or "") != (inst or ""): crs.instructor = inst; ch = True
                    if crs.class_year != current_year: crs.class_year = current_year; ch = True
                    if crs.department_id != self.current_dept_id: crs.department_id = self.current_dept_id; ch = True
                    if ch: updated += 1
                else:
                    s.add(Course(code=code, name=name, instructor=inst,
                                 class_year=current_year, department_id=self.current_dept_id))
                    added += 1
            s.commit()
        except Exception as e:
            s.rollback(); QMessageBox.critical(self, "Hata", f"İçe aktarma hatası:\n{e}"); return
        finally:
            s.close()

        if hasattr(self, "crs_win"): self.crs_win.load_courses()
        if hasattr(self, "stu_win"): self.stu_win.load_students()

        QMessageBox.information(self, "Tamamlandı",
                                f"Ders listesi işlendi.\nYeni: {added}\nGüncellenen: {updated}")

    
    def import_students_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Öğrenci Excel Seç", "",
                                              "Excel Files (*.xlsx *.xls);;All Files (*)")
        if not path: return
        try:
            import pandas as pd
        except Exception:
            QMessageBox.critical(self, "Hata", "pandas yok. Kurulum:\npip install pandas openpyxl"); return

        QApplication.setOverrideCursor(Qt.WaitCursor); QApplication.processEvents()
        try:
            df = pd.read_excel(path, dtype=str)
        except Exception as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.critical(self, "Hata", f"Excel okunamadı:\n{e}"); return
        QApplication.restoreOverrideCursor(); QApplication.processEvents()

        C_NUM, C_NAME, C_YEAR, C_CODE = "Öğrenci No", "Ad Soyad", "Sınıf", "Ders"
        for need in (C_NUM, C_NAME):
            if need not in df.columns:
                QMessageBox.warning(self, "Uyarı", f"Excel'de '{need}' sütunu bulunmalı."); return
        if C_YEAR not in df.columns: df[C_YEAR] = None
        if C_CODE not in df.columns: df[C_CODE] = None

        def parse_year(s):
            if not isinstance(s, str): return None
            m = re.search(r"(\d+)", s)
            return int(m.group(1)) if m else None

        s = SessionLocal()
        added = updated = skipped = 0
        enroll_created = 0


        try:
            for _, row in df.iterrows():
                num  = str(row.get(C_NUM, "") or "").strip()
                name = str(row.get(C_NAME, "") or "").strip()
                year = parse_year(row.get(C_YEAR, ""))
                code = str(row.get(C_CODE, "") or "").strip()

                if not num or not name:
                    skipped += 1
                    continue




                st = s.query(Student).filter_by(number=num).first()
                if st:
                    ch = False
                    if st.name != name: st.name = name; ch = True
                    if year is not None and st.class_year != year: st.class_year = year; ch = True
                    if st.department_id != self.current_dept_id: st.department_id = self.current_dept_id; ch = True
                    if ch: updated += 1
                else:
                    st = Student(number=num, name=name, class_year=year, department_id=self.current_dept_id)
                    s.add(st); s.flush()
                    added += 1

                


                if code:
                    crs = (s.query(Course)
                           .filter(Course.code == code, Course.department_id == self.current_dept_id)
                           .first())
                    if crs:
                        exists = s.query(Enrollment).filter_by(student_id=st.id, course_id=crs.id).first()
                        if not exists:
                            s.add(Enrollment(student_id=st.id, course_id=crs.id))
                            enroll_created += 1

            s.commit()
        except Exception as e:
            s.rollback(); QMessageBox.critical(self, "Hata", f"İçe aktarma hatası:\n{e}"); return
        finally:
            s.close()

        if hasattr(self, "crs_win"): self.crs_win.load_courses()
        if hasattr(self, "stu_win"): self.stu_win.load_students()

        QMessageBox.information(
            self, "Tamamlandı",
            f"Öğrenci listesi işlendi.\n"
            f"Yeni: {added} | Güncellenen: {updated} | Atlanan: {skipped}\n"
            f"Yeni kayıtlı ders (enrollment): {enroll_created}"
        )


class LoginWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Dinamik Sınav Takvimi — Giriş")
        self.resize(460, 320)
        self.session = SessionLocal()


        root = QWidget(); v = QVBoxLayout(root)
        v.setContentsMargins(24, 24, 24, 24); v.setSpacing(16)
        form = QFormLayout(); form.setLabelAlignment(Qt.AlignRight)
        self.emailEdit = QLineEdit(); self.emailEdit.setPlaceholderText("e-posta")
        self.passwordEdit = QLineEdit(); self.passwordEdit.setPlaceholderText("şifre")
        self.passwordEdit.setEchoMode(QLineEdit.Password)
        self.deptCombo = QComboBox()
        for d in self.session.query(Department).order_by(Department.name).all():
            self.deptCombo.addItem(d.name, d.id)
        form.addRow("E-posta:", self.emailEdit)
        form.addRow("Şifre:", self.passwordEdit)
        form.addRow("Bölüm:", self.deptCombo)
        v.addLayout(form)
        row = QHBoxLayout(); row.addStretch(1)
        self.loginBtn = QPushButton("Giriş"); self.loginBtn.setDefault(True)
        row.addWidget(self.loginBtn); v.addLayout(row)
        self.loginBtn.clicked.connect(self.do_login)
        self.passwordEdit.returnPressed.connect(self.do_login)
        self.setCentralWidget(root)




    def do_login(self):
        if self.deptCombo.count() == 0:
            QMessageBox.warning(self, "Eksik", "Sistemde bölüm bulunmuyor."); return
        dept_id = int(self.deptCombo.currentData())
        user = verify(self.session, self.emailEdit.text().strip(), self.passwordEdit.text(), dept_id)
        if not user:
            QMessageBox.warning(self, "Hatalı giriş", "Bilgiler veya bölüm seçimi hatalı."); return
        self.main = MainWindow(user, department_id=dept_id); self.main.show(); self.close()

def main():
    ensure_schema_and_seed()
    s = SessionLocal()
    try:
        ensure_bootstrap_user(s)
    finally:
        s.close()
    app = QApplication(sys.argv)
    w = LoginWindow()
    w.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
