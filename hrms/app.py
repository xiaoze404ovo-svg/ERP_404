# -*- coding: utf-8 -*-
"""HRMS - 企业人力资源管理系统"""
import sqlite3
import hashlib
import json
import os
import io
import csv
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, send_file, flash, make_response
)

# ==================== 配置 ====================
app = Flask(__name__)
app.secret_key = 'hrms-secret-key-2026'
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'erp.db')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# ==================== 数据库工具 ====================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def query_db(sql, args=(), one=False):
    conn = get_db()
    cur = conn.execute(sql, args)
    rv = [dict(row) for row in cur.fetchall()]
    conn.close()
    return (rv[0] if rv else None) if one else rv

def execute_db(sql, args=()):
    conn = get_db()
    cur = conn.execute(sql, args)
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected

def execute_many(sql, args_list):
    conn = get_db()
    cur = conn.executemany(sql, args_list)
    conn.commit()
    affected = cur.rowcount
    conn.close()
    return affected

# ==================== 登录与权限装饰器 ====================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('权限不足，需要管理员权限', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# ==================== 路由 - 登录 ====================
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        user = query_db(
            "SELECT * FROM hr_users WHERE username=? AND password_hash=? AND is_active=1",
            (username, pwd_hash), one=True
        )
        if user:
            session.permanent = True
            session['user_id'] = user['user_id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = user['full_name']
            execute_db(
                "UPDATE hr_users SET last_login=datetime('now','localtime') WHERE user_id=?",
                (user['user_id'],)
            )
            return redirect(url_for('dashboard'))
        flash('用户名或密码错误', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    old_pwd = request.form.get('old_password', '')
    new_pwd = request.form.get('new_password', '')
    old_hash = hashlib.sha256(old_pwd.encode()).hexdigest()
    user = query_db(
        "SELECT * FROM hr_users WHERE user_id=? AND password_hash=?",
        (session['user_id'], old_hash), one=True
    )
    if not user:
        return jsonify({'success': False, 'message': '原密码错误'})
    new_hash = hashlib.sha256(new_pwd.encode()).hexdigest()
    execute_db("UPDATE hr_users SET password_hash=? WHERE user_id=?", (new_hash, session['user_id']))
    return jsonify({'success': True, 'message': '密码修改成功'})

# ==================== 路由 - 仪表盘 ====================
@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/dashboard/stats')
@login_required
def dashboard_stats():
    """获取仪表盘统计数据"""
    total_employees = query_db("SELECT COUNT(*) as cnt FROM app_emp WHERE stop_flag='N'", one=True)['cnt']
    total_depts = query_db("SELECT COUNT(*) as cnt FROM app_dept WHERE stop_flag='N'", one=True)['cnt']
    active_emps = query_db(
        "SELECT COUNT(*) as cnt FROM hr_employee_ext WHERE work_status='active'", one=True
    )['cnt']
    if active_emps == 0 and total_employees > 0:
        active_emps = total_employees
    monthly_changes = query_db(
        "SELECT COUNT(*) as cnt FROM hr_personnel_changes WHERE strftime('%Y-%m', change_date)=strftime('%Y-%m', 'now')",
        one=True
    )['cnt']
    return jsonify({
        'total_employees': total_employees,
        'total_departments': total_depts,
        'active_employees': active_emps,
        'monthly_changes': monthly_changes,
        'role': session.get('role')
    })

@app.route('/api/dashboard/dept_distribution')
@login_required
def dept_distribution():
    rows = query_db("""
        SELECT d.dept_name, COUNT(e.emp_id) as count
        FROM app_dept d
        LEFT JOIN app_emp e ON d.dept_id=e.dept_id AND e.stop_flag='N'
        WHERE d.stop_flag='N'
        GROUP BY d.dept_id
        ORDER BY count DESC
    """)
    return jsonify({
        'labels': [r['dept_name'] for r in rows],
        'values': [r['count'] for r in rows]
    })

@app.route('/api/dashboard/salary_stats')
@login_required
def salary_stats():
    # 最近工资期间
    ws = query_db("SELECT voucher_id, data_month FROM wage_set ORDER BY voucher_id DESC LIMIT 1", one=True)
    if not ws:
        return jsonify({'avg_salary': 0, 'max_salary': 0, 'min_salary': 0, 'total_payroll': 0})
    data = query_db("""
        SELECT wd.emp_id, wd.val
        FROM wage_data wd
        WHERE wd.voucher_id=? AND wd.wage_subject_id='700'
    """, (ws['voucher_id'],))
    amounts = [r['val'] for r in data if r['val']]
    if not amounts:
        return jsonify({'avg_salary': 0, 'max_salary': 0, 'min_salary': 0, 'total_payroll': 0})
    return jsonify({
        'avg_salary': round(sum(amounts)/len(amounts), 2),
        'max_salary': max(amounts),
        'min_salary': min(amounts),
        'total_payroll': sum(amounts)
    })

@app.route('/api/dashboard/attendance_trend')
@login_required
def attendance_trend():
    rows = query_db("""
        SELECT year_month, SUM(late_times) as late, SUM(absent_days) as absent,
               SUM(leave_days) as leaves, SUM(overtime_hours) as overtime
        FROM hr_attendance_summary
        GROUP BY year_month ORDER BY year_month DESC LIMIT 6
    """)
    return jsonify([dict(r) for r in rows])

# ==================== 路由 - 员工管理 ====================
@app.route('/employees')
@login_required
def employees():
    return render_template('employees.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/employees')
@login_required
def list_employees():
    """员工列表（支持筛选）"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    search = request.args.get('search', '').strip()
    dept_id = request.args.get('dept_id', '').strip()
    status = request.args.get('status', '').strip()
    
    where = []
    params = []
    if search:
        where.append("(e.name LIKE ? OR e.emp_id LIKE ? OR e.mobile LIKE ?)")
        params.extend([f'%{search}%'] * 3)
    if dept_id:
        where.append("e.dept_id=?")
        params.append(dept_id)
    if status == 'resigned':
        where.append("(e.stop_flag='Y' OR COALESCE(ext.work_status,'active')='resigned')")
    elif status == 'active':
        where.append("e.stop_flag='N' AND COALESCE(ext.work_status,'active')='active'")
    elif status == 'leave':
        where.append("COALESCE(ext.work_status,'active')='leave'")
    elif status == 'retired':
        where.append("COALESCE(ext.work_status,'active')='retired'")
    else:
        where.append("e.stop_flag='N'")
    
    where_clause = " AND ".join(where) if where else "1=1"
    total = query_db(
        f"SELECT COUNT(*) as cnt FROM app_emp e LEFT JOIN hr_employee_ext ext ON e.emp_id=ext.emp_id WHERE {where_clause}",
        params, one=True
    )['cnt']
    
    offset = (page - 1) * per_page
    rows = query_db(f"""
        SELECT e.emp_id, e.name, e.dept_id, d.dept_name, e.post_id,
               e.mobile, e.email, e.stop_flag,
               COALESCE(ext.gender,'') as gender,
               COALESCE(ext.hire_date,'') as hire_date,
               COALESCE(ext.work_status,'active') as work_status,
               COALESCE(ext.education,'') as education
        FROM app_emp e
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        LEFT JOIN hr_employee_ext ext ON e.emp_id=ext.emp_id
        WHERE {where_clause}
        ORDER BY e.emp_id
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    
    return jsonify({
        'total': total,
        'page': page,
        'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'data': rows
    })

@app.route('/api/employees/<emp_id>')
@login_required
def get_employee(emp_id):
    row = query_db("""
        SELECT e.*, d.dept_name,
               COALESCE(ext.gender,'') as gender,
               COALESCE(ext.birth_date,'') as birth_date,
               COALESCE(ext.id_card,'') as id_card,
               COALESCE(ext.education,'') as education,
               COALESCE(ext.graduate_school,'') as graduate_school,
               COALESCE(ext.major,'') as major,
               COALESCE(ext.hire_date,'') as hire_date,
               COALESCE(ext.work_status,'active') as work_status,
               COALESCE(ext.contract_type,'') as contract_type,
               COALESCE(ext.contract_end_date,'') as contract_end_date,
               COALESCE(ext.emergency_contact,'') as emergency_contact,
               COALESCE(ext.emergency_phone,'') as emergency_phone,
               COALESCE(ext.home_address,'') as home_address,
               COALESCE(ext.marital_status,'') as marital_status,
               COALESCE(ext.nationality,'') as nationality
        FROM app_emp e
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        LEFT JOIN hr_employee_ext ext ON e.emp_id=ext.emp_id
        WHERE e.emp_id=?
    """, (emp_id,), one=True)
    if not row:
        return jsonify({'error': '员工不存在'}), 404
    return jsonify(row)

@app.route('/api/employees', methods=['POST'])
@login_required
def create_employee():
    data = request.json
    emp_id = data.get('emp_id', '').strip()
    name = data.get('name', '').strip()
    dept_id = data.get('dept_id', '').strip()
    
    if not emp_id or not name:
        return jsonify({'success': False, 'message': '员工编号和姓名为必填项'})
    
    existing = query_db("SELECT emp_id FROM app_emp WHERE emp_id=?", (emp_id,), one=True)
    if existing:
        return jsonify({'success': False, 'message': f'员工编号 {emp_id} 已存在'})
    
    execute_db(
        "INSERT INTO app_emp (emp_id, name, dept_id, post_id, mobile, email, stop_flag) VALUES (?,?,?,?,?,?,?)",
        (emp_id, name, dept_id, data.get('post_id',''), data.get('mobile',''), data.get('email',''), 'N')
    )
    execute_db("""
        INSERT INTO hr_employee_ext (emp_id, gender, birth_date, id_card, education, graduate_school,
            major, hire_date, work_status, contract_type, contract_end_date, emergency_contact,
            emergency_phone, home_address, marital_status, nationality)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (emp_id, data.get('gender',''), data.get('birth_date',''), data.get('id_card',''),
          data.get('education',''), data.get('graduate_school',''), data.get('major',''),
          data.get('hire_date',''), data.get('work_status','active'), data.get('contract_type',''),
          data.get('contract_end_date',''), data.get('emergency_contact',''),
          data.get('emergency_phone',''), data.get('home_address',''),
          data.get('marital_status',''), data.get('nationality','')))
    
    return jsonify({'success': True, 'message': '员工创建成功'})

@app.route('/api/employees/<emp_id>', methods=['PUT'])
@login_required
def update_employee(emp_id):
    data = request.json
    execute_db(
        "UPDATE app_emp SET name=?, dept_id=?, post_id=?, mobile=?, email=? WHERE emp_id=?",
        (data.get('name',''), data.get('dept_id',''), data.get('post_id',''),
         data.get('mobile',''), data.get('email',''), emp_id)
    )
    existing_ext = query_db("SELECT emp_id FROM hr_employee_ext WHERE emp_id=?", (emp_id,), one=True)
    if existing_ext:
        execute_db("""
            UPDATE hr_employee_ext SET gender=?, birth_date=?, id_card=?, education=?,
                graduate_school=?, major=?, hire_date=?, work_status=?, contract_type=?,
                contract_end_date=?, emergency_contact=?, emergency_phone=?, home_address=?,
                marital_status=?, nationality=?, updated_at=datetime('now','localtime')
            WHERE emp_id=?
        """, (data.get('gender',''), data.get('birth_date',''), data.get('id_card',''),
              data.get('education',''), data.get('graduate_school',''), data.get('major',''),
              data.get('hire_date',''), data.get('work_status','active'), data.get('contract_type',''),
              data.get('contract_end_date',''), data.get('emergency_contact',''),
              data.get('emergency_phone',''), data.get('home_address',''),
              data.get('marital_status',''), data.get('nationality',''), emp_id))
    else:
        execute_db("""
            INSERT INTO hr_employee_ext (emp_id, gender, birth_date, id_card, education, graduate_school,
                major, hire_date, work_status, contract_type, contract_end_date, emergency_contact,
                emergency_phone, home_address, marital_status, nationality)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (emp_id, data.get('gender',''), data.get('birth_date',''), data.get('id_card',''),
              data.get('education',''), data.get('graduate_school',''), data.get('major',''),
              data.get('hire_date',''), data.get('work_status','active'), data.get('contract_type',''),
              data.get('contract_end_date',''), data.get('emergency_contact',''),
              data.get('emergency_phone',''), data.get('home_address',''),
              data.get('marital_status',''), data.get('nationality','')))
    return jsonify({'success': True, 'message': '员工信息更新成功'})

@app.route('/api/employees/<emp_id>/dismiss', methods=['POST'])
@login_required
def dismiss_employee(emp_id):
    """撤职/离职/退休"""
    data = request.json or {}
    dismiss_type = data.get('dismiss_type', 'resign')
    dismiss_date = data.get('dismiss_date', datetime.now().strftime('%Y-%m-%d'))
    reason = data.get('reason', '')
    
    # 状态映射
    status_map = {'resign': 'resigned', 'fire': 'resigned', 'retire': 'retired'}
    work_status = status_map.get(dismiss_type, 'resigned')
    
    # 获取员工当前信息用于变动记录
    emp = query_db("SELECT name, dept_id FROM app_emp WHERE emp_id=?", (emp_id,), one=True)
    if not emp:
        return jsonify({'success': False, 'message': '员工不存在'}), 404
    
    # 更新员工状态
    execute_db("UPDATE app_emp SET stop_flag='Y' WHERE emp_id=?", (emp_id,))
    execute_db("UPDATE hr_employee_ext SET work_status=? WHERE emp_id=?", (work_status, emp_id))
    
    # 自动记录人事变动
    change_type_map = {'resign': 'resign', 'fire': 'resign', 'retire': 'retire'}
    change_type = change_type_map.get(dismiss_type, 'resign')
    execute_db("""
        INSERT INTO hr_personnel_changes
        (emp_id, change_type, change_date, reason, remark, operator_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (emp_id, change_type, dismiss_date, reason,
          f'原部门：{emp["dept_id"]}，类型：{"自动离职" if dismiss_type=="resign" else "辞退" if dismiss_type=="fire" else "退休"}',
          session['user_id']))
    
    return jsonify({'success': True, 'message': '操作成功'})

@app.route('/api/employees/<emp_id>/rehire', methods=['POST'])
@login_required
def rehire_employee(emp_id):
    """返聘已离职员工"""
    emp = query_db("SELECT name, dept_id FROM app_emp WHERE emp_id=?", (emp_id,), one=True)
    if not emp:
        return jsonify({'success': False, 'message': '员工不存在'}), 404
    
    execute_db("UPDATE app_emp SET stop_flag='N' WHERE emp_id=?", (emp_id,))
    execute_db("UPDATE hr_employee_ext SET work_status='active' WHERE emp_id=?", (emp_id,))
    
    execute_db("""
        INSERT INTO hr_personnel_changes
        (emp_id, change_type, change_date, reason, operator_id)
        VALUES (?, 'return', datetime('now','localtime'), ?, ?)
    """, (emp_id, f'返聘，部门：{emp["dept_id"]}', session['user_id']))
    
    return jsonify({'success': True, 'message': '返聘成功'})

@app.route('/api/departments/list')
@login_required
def dept_list_for_select():
    rows = query_db("SELECT dept_id, dept_name FROM app_dept WHERE stop_flag='N' ORDER BY order_id")
    return jsonify(rows)

# ==================== 路由 - 部门管理 ====================
@app.route('/departments')
@login_required
def departments_page():
    return render_template('departments.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/departments')
@login_required
def list_departments():
    rows = query_db("""
        SELECT d.dept_id, d.dept_name, d.parent_dept_id, d.company_id,
               c.company_name, d.stop_flag, d.order_id,
               (SELECT COUNT(*) FROM app_emp WHERE dept_id=d.dept_id AND stop_flag='N') as emp_count
        FROM app_dept d
        LEFT JOIN app_company c ON d.company_id=c.company_id
        ORDER BY d.order_id, d.dept_id
    """)
    return jsonify(rows)

@app.route('/api/departments', methods=['POST'])
@login_required
def create_department():
    data = request.json
    dept_id = data.get('dept_id', '').strip()
    dept_name = data.get('dept_name', '').strip()
    if not dept_id or not dept_name:
        return jsonify({'success': False, 'message': '部门编号和名称为必填项'})
    existing = query_db("SELECT dept_id FROM app_dept WHERE dept_id=?", (dept_id,), one=True)
    if existing:
        return jsonify({'success': False, 'message': f'部门编号 {dept_id} 已存在'})
    execute_db(
        "INSERT INTO app_dept (dept_id, dept_name, parent_dept_id, company_id, stop_flag, order_id) VALUES (?,?,?,?,?,?)",
        (dept_id, dept_name, data.get('parent_dept_id',''), data.get('company_id','01'), 'N', data.get('order_id',0))
    )
    return jsonify({'success': True, 'message': '部门创建成功'})

@app.route('/api/departments/<dept_id>', methods=['PUT'])
@login_required
def update_department(dept_id):
    data = request.json
    execute_db(
        "UPDATE app_dept SET dept_name=?, parent_dept_id=?, order_id=? WHERE dept_id=?",
        (data.get('dept_name',''), data.get('parent_dept_id',''), data.get('order_id',0), dept_id)
    )
    return jsonify({'success': True, 'message': '部门信息更新成功'})

@app.route('/api/departments/<dept_id>', methods=['DELETE'])
@login_required
def delete_department(dept_id):
    emp_count = query_db(
        "SELECT COUNT(*) as cnt FROM app_emp WHERE dept_id=? AND stop_flag='N'", (dept_id,), one=True
    )['cnt']
    if emp_count > 0:
        return jsonify({'success': False, 'message': f'该部门下还有 {emp_count} 名在职员工，无法删除'})
    execute_db("UPDATE app_dept SET stop_flag='Y' WHERE dept_id=?", (dept_id,))
    return jsonify({'success': True, 'message': '部门已停用'})

# ==================== 路由 - 考勤管理 ====================
@app.route('/attendance')
@login_required
def attendance_page():
    return render_template('attendance.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/attendance')
@login_required
def list_attendance():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    emp_name = request.args.get('emp_name', '').strip()
    year_month = request.args.get('year_month', '').strip()
    
    where = ["1=1"]
    params = []
    if emp_name:
        where.append("e.name LIKE ?")
        params.append(f'%{emp_name}%')
    if year_month:
        where.append("s.year_month=?")
        params.append(year_month)
    
    where_clause = " AND ".join(where)
    total = query_db(
        f"SELECT COUNT(*) as cnt FROM hr_attendance_summary s JOIN app_emp e ON s.emp_id=e.emp_id WHERE {where_clause}",
        params, one=True
    )['cnt']
    
    offset = (page - 1) * per_page
    rows = query_db(f"""
        SELECT s.*, e.name, d.dept_name
        FROM hr_attendance_summary s
        JOIN app_emp e ON s.emp_id=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        WHERE {where_clause}
        ORDER BY s.year_month DESC, e.name
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    
    return jsonify({
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'data': rows
    })

@app.route('/api/attendance/raw')
@login_required
def list_raw_attendance():
    """原始打卡记录"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    where = ["1=1"]
    params = []
    if date_from:
        where.append("t.mark_date>=?")
        params.append(date_from.replace('-', ''))
    if date_to:
        where.append("t.mark_date<=?")
        params.append(date_to.replace('-', ''))
    
    where_clause = " AND ".join(where)
    total = query_db(
        f"SELECT COUNT(*) as cnt FROM timer_original_rec t WHERE {where_clause}", params, one=True
    )['cnt']
    
    offset = (page - 1) * per_page
    rows = query_db(f"""
        SELECT t.rec_id, t.card_no, t.mark_date, t.mark_time, t.rec_io_flag,
               e.name, e.emp_id, d.dept_name
        FROM timer_original_rec t
        LEFT JOIN app_emp e ON t.card_no=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        WHERE {where_clause}
        ORDER BY t.mark_date DESC, t.mark_time DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    
    return jsonify({
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'data': rows
    })

@app.route('/api/attendance/summarize', methods=['POST'])
@login_required
def summarize_attendance():
    """从原始打卡记录汇总考勤"""
    data = request.json
    year_month = data.get('year_month', datetime.now().strftime('%Y%m'))
    
    # 按员工统计打卡次数和出勤天数
    raw = query_db("""
        SELECT t.card_no, t.mark_date,
               COUNT(*) as punch_count,
               MIN(t.mark_time) as first_punch,
               MAX(t.mark_time) as last_punch
        FROM timer_original_rec t
        WHERE t.mark_date LIKE ? || '%'
        GROUP BY t.card_no, t.mark_date
    """, (year_month,))
    
    count = 0
    all_emps = query_db("SELECT emp_id FROM app_emp WHERE stop_flag='N'")
    emp_ids = {r['emp_id'] for r in all_emps}
    
    for r in raw:
        if r['card_no'] not in emp_ids:
            continue
        late = 1 if r['first_punch'] and r['first_punch'].strip() > '0900' else 0
        work_days = 1
        execute_db("""
            INSERT INTO hr_attendance_summary (emp_id, year_month, work_days, actual_work_days, late_times)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(emp_id, year_month) DO UPDATE SET
                work_days = work_days + ?,
                actual_work_days = actual_work_days + ?,
                late_times = late_times + ?
        """, (r['card_no'], year_month, work_days, work_days, late, work_days, work_days, late))
        count += 1
    
    # 也从未汇总的员工添加记录
    for emp_id in emp_ids:
        existing = query_db(
            "SELECT emp_id FROM hr_attendance_summary WHERE emp_id=? AND year_month=?",
            (emp_id, year_month), one=True
        )
        if not existing:
            execute_db(
                "INSERT INTO hr_attendance_summary (emp_id, year_month, work_days, actual_work_days) VALUES (?,?,?,?)",
                (emp_id, year_month, 0, 0)
            )
    
    return jsonify({'success': True, 'message': f'考勤汇总完成，处理 {count} 条记录'})

# ==================== 路由 - 薪酬管理 ====================
@app.route('/salary')
@login_required
def salary_page():
    return render_template('salary.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/salary/sets')
@login_required
def salary_sets():
    rows = query_db("SELECT voucher_id as set_id, data_month, title, wage_set_type as state FROM wage_set ORDER BY voucher_id DESC")
    return jsonify(rows)

@app.route('/api/salary/subjects')
@login_required
def salary_subjects():
    rows = query_db("SELECT wage_subject_id as subject_id, wage_subject_name as subject_name, order_id, note_info as group_name FROM wage_subject ORDER BY order_id")
    return jsonify(rows)

@app.route('/api/salary')
@login_required
def list_salary():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    set_id = request.args.get('set_id', '').strip()
    emp_name = request.args.get('emp_name', '').strip()
    
    # 转成voucher_id
    if not set_id:
        ws = query_db("SELECT voucher_id FROM wage_set ORDER BY voucher_id DESC LIMIT 1", one=True)
        voucher_id = ws['voucher_id'] if ws else ''
    else:
        voucher_id = set_id
    
    where = ["wd.voucher_id=?"]
    params = [voucher_id]
    if emp_name:
        where.append("e.name LIKE ?")
        params.append(f'%{emp_name}%')
    
    where_clause = " AND ".join(where)
    
    # 获取所有员工+工资科目的数据
    rows = query_db(f"""
        SELECT wd.emp_id, wd.wage_subject_id, wd.val,
               e.name, d.dept_name, sj.wage_subject_name
        FROM wage_data wd
        JOIN app_emp e ON wd.emp_id=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        JOIN wage_subject sj ON wd.wage_subject_id=sj.wage_subject_id
        WHERE {where_clause}
        ORDER BY e.name, sj.order_id
    """, params)
    
    # 转置为每个科目一列
    emp_data = {}
    for r in rows:
        eid = r['emp_id']
        if eid not in emp_data:
            emp_data[eid] = {
                'emp_id': eid, 'name': r['name'],
                'dept_name': r['dept_name'],
                'subjects': {}
            }
        emp_data[eid]['subjects'][r['wage_subject_name']] = r['val']
    
    total = len(emp_data)
    items = list(emp_data.values())
    offset = (page - 1) * per_page
    page_items = items[offset:offset + per_page]
    
    subjects = query_db("SELECT wage_subject_id as subject_id, wage_subject_name as subject_name FROM wage_subject ORDER BY order_id")
    
    return jsonify({
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'data': page_items,
        'subjects': subjects,
        'current_set': str(voucher_id)
    })

# ==================== 路由 - 人事变动 ====================
@app.route('/changes')
@login_required
def changes_page():
    return render_template('changes.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/changes')
@login_required
def list_changes():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    change_type = request.args.get('change_type', '').strip()
    date_from = request.args.get('date_from', '').strip()
    date_to = request.args.get('date_to', '').strip()
    
    where = ["1=1"]
    params = []
    if change_type:
        where.append("c.change_type=?")
        params.append(change_type)
    if date_from:
        where.append("c.change_date>=?")
        params.append(date_from)
    if date_to:
        where.append("c.change_date<=?")
        params.append(date_to)
    
    where_clause = " AND ".join(where)
    total = query_db(
        f"SELECT COUNT(*) as cnt FROM hr_personnel_changes c JOIN app_emp e ON c.emp_id=e.emp_id WHERE {where_clause}",
        params, one=True
    )['cnt']
    
    offset = (page - 1) * per_page
    rows = query_db(f"""
        SELECT c.*, e.name, e.dept_id, d.dept_name,
               od.dept_name as old_dept_name, nd.dept_name as new_dept_name
        FROM hr_personnel_changes c
        JOIN app_emp e ON c.emp_id=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        LEFT JOIN app_dept od ON c.old_dept_id=od.dept_id
        LEFT JOIN app_dept nd ON c.new_dept_id=nd.dept_id
        WHERE {where_clause}
        ORDER BY c.change_date DESC, c.change_id DESC
        LIMIT ? OFFSET ?
    """, params + [per_page, offset])
    
    change_types = {
        'hire': '入职', 'resign': '离职', 'transfer': '调岗',
        'promotion': '晋升', 'demotion': '降职', 'leave': '请假',
        'return': '返岗', 'contract_renew': '续约'
    }
    for r in rows:
        r['change_type_name'] = change_types.get(r['change_type'], r['change_type'])
    
    return jsonify({
        'total': total, 'page': page, 'per_page': per_page,
        'total_pages': max(1, (total + per_page - 1) // per_page),
        'data': rows
    })

@app.route('/api/changes', methods=['POST'])
@login_required
def create_change():
    data = request.json
    execute_db("""
        INSERT INTO hr_personnel_changes
        (emp_id, change_type, change_date, old_dept_id, new_dept_id,
         old_post_id, new_post_id, old_salary, new_salary, reason, remark, operator_id)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        data['emp_id'], data['change_type'], data['change_date'],
        data.get('old_dept_id',''), data.get('new_dept_id',''),
        data.get('old_post_id',''), data.get('new_post_id',''),
        data.get('old_salary'), data.get('new_salary'),
        data.get('reason',''), data.get('remark',''),
        session['user_id']
    ))
    return jsonify({'success': True, 'message': '变动记录已添加'})

# ==================== 路由 - 报表导出 ====================
@app.route('/api/export/employees')
@login_required
def export_employees():
    rows = query_db("""
        SELECT e.emp_id as 员工编号, e.name as 姓名, d.dept_name as 部门,
               COALESCE(ext.gender,'') as 性别, COALESCE(ext.education,'') as 学历,
               COALESCE(ext.hire_date,'') as 入职日期, COALESCE(ext.work_status,'active') as 状态,
               e.mobile as 手机, e.email as 邮箱
        FROM app_emp e
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        LEFT JOIN hr_employee_ext ext ON e.emp_id=ext.emp_id
        WHERE e.stop_flag='N'
        ORDER BY e.emp_id
    """)
    return export_csv('员工信息表.csv', rows)

@app.route('/api/export/attendance')
@login_required
def export_attendance():
    year_month = request.args.get('year_month', datetime.now().strftime('%Y%m'))
    rows = query_db("""
        SELECT s.emp_id as 员工编号, e.name as 姓名, d.dept_name as 部门,
               s.year_month as 月份, s.work_days as 应出勤, s.actual_work_days as 实际出勤,
               s.late_times as 迟到次数, s.early_leave_times as 早退次数,
               s.absent_days as 旷工天数, s.leave_days as 请假天数, s.overtime_hours as 加班小时
        FROM hr_attendance_summary s
        JOIN app_emp e ON s.emp_id=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        WHERE s.year_month=?
        ORDER BY e.name
    """, (year_month,))
    return export_csv(f'考勤汇总_{year_month}.csv', rows)

@app.route('/api/export/salary')
@login_required
def export_salary():
    set_id = request.args.get('set_id', '').strip()
    if not set_id:
        ws = query_db("SELECT voucher_id FROM wage_set ORDER BY voucher_id DESC LIMIT 1", one=True)
        voucher_id = ws['voucher_id'] if ws else ''
    else:
        voucher_id = set_id
    
    rows = query_db("""
        SELECT wd.emp_id as 员工编号, e.name as 姓名, d.dept_name as 部门,
               sj.wage_subject_name as 科目, wd.val as 金额
        FROM wage_data wd
        JOIN app_emp e ON wd.emp_id=e.emp_id
        LEFT JOIN app_dept d ON e.dept_id=d.dept_id
        JOIN wage_subject sj ON wd.wage_subject_id=sj.wage_subject_id
        WHERE wd.voucher_id=?
        ORDER BY e.name, sj.order_id
    """, (voucher_id,))
    return export_csv(f'工资表_{str(voucher_id).strip()}.csv', rows)

@app.route('/api/export/changes')
@login_required
def export_changes():
    change_types = {
        'hire': '入职', 'resign': '离职', 'transfer': '调岗',
        'promotion': '晋升', 'demotion': '降职', 'leave': '请假',
        'return': '返岗', 'contract_renew': '续约'
    }
    rows = query_db("""
        SELECT c.change_id as 编号, e.name as 员工姓名, c.change_type as 变动类型,
               c.change_date as 变动日期, c.reason as 变动原因,
               c.remark as 备注, c.created_at as 记录时间
        FROM hr_personnel_changes c
        JOIN app_emp e ON c.emp_id=e.emp_id
        ORDER BY c.change_date DESC
    """)
    for r in rows:
        r['变动类型'] = change_types.get(r['变动类型'], r['变动类型'])
    return export_csv('人事变动记录.csv', rows)

def export_csv(filename, data):
    """导出CSV文件"""
    if not data:
        return jsonify({'success': False, 'message': '没有可导出的数据'})
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(data[0].keys())
    for row in data:
        writer.writerow(row.values())
    
    output.seek(0)
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv; charset=utf-8-sig'
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response

# ==================== 路由 - 用户管理（管理员） ====================
@app.route('/users')
@login_required
@admin_required
def users_page():
    return render_template('users.html',
                           user_name=session.get('full_name', session.get('username')),
                           role=session.get('role'))

@app.route('/api/users')
@login_required
@admin_required
def list_users():
    rows = query_db("SELECT user_id, username, role, full_name, is_active, last_login FROM hr_users ORDER BY username")
    return jsonify(rows)

@app.route('/api/users', methods=['POST'])
@login_required
@admin_required
def create_user():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'hr_specialist')
    full_name = data.get('full_name', '').strip()
    
    existing = query_db("SELECT username FROM hr_users WHERE username=?", (username,), one=True)
    if existing:
        return jsonify({'success': False, 'message': '用户名已存在'})
    
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    user_id = f'user_{datetime.now().strftime("%Y%m%d%H%M%S")}'
    execute_db(
        "INSERT INTO hr_users (user_id, username, password_hash, role, full_name) VALUES (?,?,?,?,?)",
        (user_id, username, pwd_hash, role, full_name)
    )
    return jsonify({'success': True, 'message': '用户创建成功'})

@app.route('/api/users/<user_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session['user_id']:
        return jsonify({'success': False, 'message': '不能删除自己'})
    execute_db("DELETE FROM hr_users WHERE user_id=?", (user_id,))
    return jsonify({'success': True, 'message': '用户已删除'})

# ==================== 启动 ====================
if __name__ == '__main__':
    print("=" * 50)
    print("  企业人力资源管理系统 (HRMS)")
    print("=" * 50)
    print(f"  数据库: {DB_PATH}")
    print("  启动地址: http://127.0.0.1:5000")
    print("  默认管理员: admin / admin123")
    print("  默认人事专员: hruser / hr123")
    print("=" * 50)
    app.run(debug=True, host='127.0.0.1', port=5000)
