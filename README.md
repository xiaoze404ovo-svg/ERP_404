# ERP_404 - 人力资源管理系统

基于企业 ERP 数据库开发的人力资源管理系统，专为企业人事部门设计，提供完整的员工生命周期管理解决方案。

---

## 功能模块

| 模块 | 说明 |
|------|------|
| 数据仪表盘 | Chart.js 可视化图表，展示员工分布、薪酬概览、考勤趋势 |
| 员工信息档案管理 | 22 个字段的完整档案，支持多条件搜索、筛选、CRUD 操作 |
| 部门与岗位架构管理 | 树形组织架构图，部门增删改，员工数统计 |
| 考勤记录追踪 | 原始打卡记录查询，月度考勤汇总，迟到/旷工/请假统计 |
| 薪酬福利管理 | 按工资期间查询薪资数据，多科目转置显示 |
| 人事变动记录 | 入职/离职/调岗/晋升/降职/续约等变动全跟踪 |
| 报表导出 | CSV 格式导出员工表、考勤表、工资表、变动记录 |
| 用户权限管理 | 管理员与人事专员双角色，安全的登录系统 |

## 技术栈

- **后端**: Python Flask + SQLite
- **前端**: Bootstrap 5 + Chart.js + jQuery + AdminLTE
- **数据库**: 基于现有 ERP 数据库 (SQLite)，扩展 HRMS 专用表

## 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/xiaoze404ovo-svg/ERP_404.git
cd ERP_404/hrms

# 2. 安装依赖
pip install flask flask-cors openpyxl

# 3. 初始化数据库
py init_db.py

# 4. 启动系统
py app.py
```

访问 http://127.0.0.1:5000

## 默认账户

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 管理员 | `admin` | `admin123` | 全部功能 + 用户管理 |
| 人事专员 | `hruser` | `hr123` | 除用户管理外的所有功能 |

## 项目结构

```
ERP_404/
├── erp.db              # 企业 ERP 数据库
├── .gitignore
├── VERSION
├── README.md
├── push_to_github.py   # GitHub API 上传脚本
└── hrms/
    ├── app.py          # Flask 主应用
    ├── init_db.py      # 数据库初始化
    ├── requirements.txt
    ├── templates/
    │   ├── base.html        # 基础模板
    │   ├── login.html       # 登录页
    │   ├── dashboard.html   # 仪表盘
    │   ├── employees.html   # 员工管理
    │   ├── departments.html # 部门管理
    │   ├── attendance.html  # 考勤管理
    │   ├── salary.html      # 薪酬管理
    │   ├── changes.html     # 人事变动
    │   └── users.html       # 用户管理
    └── static/
        ├── css/
        └── js/
```

## 版本

**v0.0.1** - 2026-05-11
