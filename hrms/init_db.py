# -*- coding: utf-8 -*-
"""HRMS 数据库初始化脚本 - 在现有ERP数据库上创建HRMS专用表"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'erp.db')

def init_hrms_database():
    """初始化HRMS模块所需的额外表和数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. HRMS用户表 - 用于登录和权限管理
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_users (
            user_id TEXT PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            emp_id TEXT,
            role TEXT NOT NULL DEFAULT 'hr_specialist' CHECK(role IN ('admin', 'hr_specialist')),
            full_name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            last_login TEXT
        )
    ''')
    
    # 2. 人事变动记录表（无外键约束，因app_emp表未定义主键）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_personnel_changes (
            change_id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            change_type TEXT NOT NULL CHECK(change_type IN (
                'hire','resign','transfer','promotion','demotion','leave','return','contract_renew'
            )),
            change_date TEXT NOT NULL,
            old_dept_id TEXT,
            new_dept_id TEXT,
            old_post_id TEXT,
            new_post_id TEXT,
            old_salary REAL,
            new_salary REAL,
            reason TEXT,
            remark TEXT,
            operator_id TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    
    # 3. 员工扩展信息表（无外键约束）
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_employee_ext (
            emp_id TEXT PRIMARY KEY,
            gender TEXT,
            birth_date TEXT,
            id_card TEXT,
            nationality TEXT,
            marital_status TEXT,
            education TEXT,
            graduate_school TEXT,
            major TEXT,
            hire_date TEXT,
            work_status TEXT DEFAULT 'active' CHECK(work_status IN ('active','resigned','leave','retired')),
            contract_type TEXT,
            contract_end_date TEXT,
            emergency_contact TEXT,
            emergency_phone TEXT,
            home_address TEXT,
            photo_path TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        )
    ''')
    
    # 4. 考勤汇总表
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hr_attendance_summary (
            summary_id INTEGER PRIMARY KEY AUTOINCREMENT,
            emp_id TEXT NOT NULL,
            year_month TEXT NOT NULL,
            work_days INTEGER DEFAULT 0,
            actual_work_days INTEGER DEFAULT 0,
            late_times INTEGER DEFAULT 0,
            early_leave_times INTEGER DEFAULT 0,
            absent_days INTEGER DEFAULT 0,
            leave_days REAL DEFAULT 0,
            overtime_hours REAL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(emp_id, year_month)
        )
    ''')
    
    # 检查并插入默认管理员账户
    cursor.execute("SELECT COUNT(*) FROM hr_users")
    if cursor.fetchone()[0] == 0:
        admin_pwd = 'admin123'
        import hashlib
        pwd_hash = hashlib.sha256(admin_pwd.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO hr_users (user_id, username, password_hash, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            ('admin', 'admin', pwd_hash, 'admin', '系统管理员', 1)
        )
        # 创建默认人事专员账户
        specialist_pwd = 'hr123'
        pwd_hash2 = hashlib.sha256(specialist_pwd.encode()).hexdigest()
        cursor.execute(
            "INSERT INTO hr_users (user_id, username, password_hash, role, full_name, is_active) VALUES (?, ?, ?, ?, ?, ?)",
            ('hr001', 'hruser', pwd_hash2, 'hr_specialist', '人事专员', 1)
        )
        print("已创建默认用户：admin/admin123（管理员）, hruser/hr123（人事专员）")
    
    conn.commit()
    conn.close()
    print("HRMS 数据库初始化完成！")

if __name__ == '__main__':
    init_hrms_database()
