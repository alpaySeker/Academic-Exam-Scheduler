from sqlalchemy import Column, Integer, String, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from core.db import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=True)
    email = Column(String(150), unique=True, nullable=False)
    password_hash = Column(String(200), nullable=False)
    role = Column(String(50), nullable=True)  
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)  
    department = relationship("Department")




class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    classrooms = relationship("Classroom", back_populates="department")



class Classroom(Base):
    __tablename__ = "classrooms"
    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(120), nullable=False)
    capacity = Column(Integer, default=1)
    cols = Column(Integer, default=1)
    rows = Column(Integer, default=1)
    desk_group = Column(Integer, default=1)
    department = relationship("Department", back_populates="classrooms")




class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True)
    number = Column(String(30), unique=True, nullable=False)  
    name = Column(String(150), nullable=False)
    class_year = Column(Integer, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    enrollments = relationship(
        "Enrollment",
        back_populates="student",
        cascade="all, delete-orphan",
        overlaps="courses,students,enrollments"
    )

    courses = relationship(
        "Course",
        secondary="enrollments",
        back_populates="students",
        overlaps="enrollments,students,courses"
    )

    department = relationship("Department")



class Course(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True)
    code = Column(String(50), unique=True, nullable=False)  
    name = Column(String(200), nullable=False)
    instructor = Column(String(150), nullable=True)
    class_year = Column(Integer, nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    
    enrollments = relationship(
        "Enrollment",
        back_populates="course",
        cascade="all, delete-orphan",
        overlaps="students,courses,enrollments"
    )

    students = relationship(
        "Student",
        secondary="enrollments",
        back_populates="courses",
        overlaps="enrollments,students,courses"
    )
    
    department = relationship("Department")



class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(Integer, primary_key=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)
    student = relationship("Student", back_populates="enrollments", overlaps="courses,students,enrollments")
    course = relationship("Course", back_populates="enrollments", overlaps="courses,students,enrollments")
    __table_args__ = (UniqueConstraint("student_id", "course_id", name="uq_student_course"),)


class Exam(Base):
    __tablename__ = "exams"
    id = Column(Integer, primary_key=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    classroom_id = Column(Integer, ForeignKey("classrooms.id"), nullable=False)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False)

    exam_date = Column(String(10), nullable=False)
    start_time = Column(String(5), nullable=True)
    end_time = Column(String(5), nullable=True)
    __table_args__ = (

        UniqueConstraint("classroom_id", "exam_date", name="uq_room_date"),
    )
