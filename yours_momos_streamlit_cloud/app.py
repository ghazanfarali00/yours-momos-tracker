
import streamlit as st
from sqlalchemy import create_engine, text
from datetime import datetime, date, timedelta
import pandas as pd
import bcrypt

st.set_page_config(page_title="Yours Momos", page_icon="🥟", layout="wide")

@st.cache_resource
def engine():
    # Configure [database] url in Streamlit Cloud Secrets.
    # Example: postgresql+psycopg2://USER:PASSWORD@HOST:5432/DBNAME
    return create_engine(st.secrets["database"]["url"], pool_pre_ping=True, pool_recycle=300)

def sql(q, params=None, fetch=False, many=False):
    with engine().begin() as c:
        r=c.execute(text(q), params or {})
        if fetch:
            return [dict(x._mapping) for x in r.fetchall()]
        return r.rowcount

def scalar(q, params=None, default=None):
    with engine().begin() as c:
        v=c.execute(text(q), params or {}).scalar()
        return default if v is None else v

def init_db():
    schema = open("schema.sql", encoding="utf-8").read()
    statements=[x.strip() for x in schema.split(";") if x.strip()]
    with engine().begin() as c:
        for s in statements:
            c.execute(text(s))

def money(paise):
    return f"₹{int(paise or 0)/100:,.2f}"

def current_business_date(dt=None):
    dt=dt or datetime.now()
    d=dt.date()
    if dt.hour < 4:
        d -= timedelta(days=1)
    return d

def ensure_day(d):
    sql("""INSERT INTO business_days(business_date,status) VALUES(:d,'OPEN')
           ON CONFLICT(business_date) DO NOTHING""", {"d":d})

def audit(action, entity="", entity_id="", details=""):
    u=st.session_state.get("user",{})
    sql("""INSERT INTO audit(username,action,entity,entity_id,details)
           VALUES(:u,:a,:e,:i,:d)""",
        {"u":u.get("username",""),"a":action,"e":entity,"i":str(entity_id),"d":details})

def totals(d):
    ensure_day(d)
    p={"d":d}
    s=sql("SELECT cash,online FROM sales WHERE business_date=:d",p,True)
    s=s[0] if s else {"cash":0,"online":0}
    normal=scalar("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE business_date=:d AND deleted=FALSE",p,0)
    alloc=scalar("""SELECT COALESCE(SUM(a.amount),0) FROM bulk_alloc a
                    JOIN bulk_expenses b ON b.id=a.bulk_id
                    WHERE a.business_date=:d AND b.deleted=FALSE""",p,0)
    rent=sql("SELECT * FROM rent WHERE business_date=:d",p,True)
    rent=rent[0] if rent else {"amount":100000,"paid":False,"method":None}
    wd=scalar("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE business_date=:d AND deleted=FALSE",p,0)
    ce=scalar("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE business_date=:d AND method='Cash' AND deleted=FALSE",p,0)
    be=scalar("SELECT COALESCE(SUM(amount),0) FROM expenses WHERE business_date=:d AND method='Bank' AND deleted=FALSE",p,0)
    bc=scalar("SELECT COALESCE(SUM(total),0) FROM bulk_expenses WHERE business_date=:d AND method='Cash' AND deleted=FALSE",p,0)
    bb=scalar("SELECT COALESCE(SUM(total),0) FROM bulk_expenses WHERE business_date=:d AND method='Bank' AND deleted=FALSE",p,0)
    wc=scalar("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE business_date=:d AND method='Cash' AND deleted=FALSE",p,0)
    wb=scalar("SELECT COALESCE(SUM(amount),0) FROM withdrawals WHERE business_date=:d AND method='Bank' AND deleted=FALSE",p,0)
    cash=s["cash"]; online=s["online"]
    rent_paid=rent["amount"] if rent["paid"] else 0
    before=cash+online-normal-alloc
    return {
        "cash":cash,"online":online,"sales":cash+online,"normal":normal,"alloc":alloc,
        "rent":rent["amount"],"rent_paid":bool(rent["paid"]),"before":before,
        "after":before-rent_paid,"withdrawal":wd,
        "net_cash":cash-ce-bc-(rent["amount"] if rent["paid"] and rent["method"]=="Cash" else 0)-wc,
        "net_bank":online-be-bb-(rent["amount"] if rent["paid"] and rent["method"]=="Bank" else 0)-wb
    }

def login():
    st.title("🥟 Yours Momos — Business Tracker")
    users=scalar("SELECT COUNT(*) FROM users",default=0)
    if users==0:
        st.subheader("First-time setup")
        st.info("Create the Owner account. This account is stored in the permanent cloud database.")
        with st.form("setup"):
            name=st.text_input("Owner name")
            username=st.text_input("Username")
            pw=st.text_input("Password",type="password")
            cpw=st.text_input("Confirm password",type="password")
            ok=st.form_submit_button("Create Owner",use_container_width=True)
        if ok:
            if not name or not username or not pw: st.error("All fields are required.")
            elif pw!=cpw: st.error("Passwords do not match.")
            else:
                try:
                    sql("""INSERT INTO users(username,name,password_hash,role)
                           VALUES(:u,:n,:h,'OWNER')""",
                        {"u":username,"n":name,"h=bcrypt":""} if False else
                        {"u":username,"n":name,"h":bcrypt.hashpw(pw.encode(),bcrypt.gensalt()).decode()})
                    st.success("Owner account created. Please log in.")
                except Exception as e:
                    st.error(f"Could not create owner: {e}")
        return
    with st.form("login"):
        u=st.text_input("Username")
        p=st.text_input("Password",type="password")
        ok=st.form_submit_button("Login",use_container_width=True)
    if ok:
        rows=sql("SELECT * FROM users WHERE username=:u AND active=TRUE",{"u":u},True)
        if rows and bcrypt.checkpw(p.encode(),rows[0]["password_hash"].encode()):
            st.session_state.user=rows[0]
            audit("LOGIN","user",rows[0]["id"])
            st.rerun()
        else:
            st.error("Invalid username or password.")

def day_picker(key):
    d=st.date_input("Business Date",current_business_date(),key=key)
    ensure_day(d)
    st.caption(f"Business period: **{d:%d-%b-%Y} 6:00 PM → {(d+timedelta(days=1)):%d-%b-%Y} 4:00 AM**")
    return d

def dashboard():
    st.header("Dashboard")
    d=day_picker("dashboard_date"); t=totals(d)
    status=scalar("SELECT status FROM business_days WHERE business_date=:d",{"d":d},default="OPEN")
    st.caption(f"Status: **{status}**")
    cols=st.columns(4)
    for col,label,val in zip(cols,["Total Sales","Normal Expenses","Profit Before Rent","Profit After Rent"],[t["sales"],t["normal"],t["before"],t["after"]]):
        col.metric(label,money(val))
    cols=st.columns(4)
    for col,label,val in zip(cols,["Cash Sales","Online Sales","Rent Paid","Owner Withdrawal"],[t["cash"],t["online"],t["rent"] if t["rent_paid"] else 0,t["withdrawal"]]):
        col.metric(label,money(val))
    st.subheader("Menu Quantities")
    rows=sql("""SELECT c.name,COALESCE(q.quantity,0) quantity
                FROM menu_categories c
                LEFT JOIN menu_qty q ON q.category_id=c.id AND q.business_date=:d
                WHERE c.active=TRUE ORDER BY c.id""",{"d":d},True)
    cols=st.columns(max(1,min(4,len(rows))))
    for i,r in enumerate(rows): cols[i%len(cols)].metric(r["name"],r["quantity"])
    a,b=st.columns(2); a.metric("Net Cash Movement",money(t["net_cash"])); b.metric("Net Bank Movement",money(t["net_bank"]))

def sales_page():
    st.header("Daily Sales")
    d=day_picker("sales_date")
    rows=sql("SELECT * FROM sales WHERE business_date=:d",{"d":d},True)
    r=rows[0] if rows else {"cash":0,"online":0,"notes":""}
    with st.form("sales"):
        cash=st.number_input("Cash Sales (₹)",min_value=0.0,value=r["cash"]/100,step=100.0)
        online=st.number_input("Online / Bank Sales (₹)",min_value=0.0,value=r["online"]/100,step=100.0)
        notes=st.text_area("Notes",value=r["notes"] or "")
        ok=st.form_submit_button("Save Sales",use_container_width=True)
    if ok:
        sql("""INSERT INTO sales(business_date,cash,online,notes,updated_by)
               VALUES(:d,:c,:o,:n,:u)
               ON CONFLICT(business_date) DO UPDATE SET cash=EXCLUDED.cash,online=EXCLUDED.online,
               notes=EXCLUDED.notes,updated_at=NOW(),updated_by=EXCLUDED.updated_by""",
            {"d":d,"c":round(cash*100),"o":round(online*100),"n":notes,"u":st.session_state.user["id"]})
        audit("UPSERT","sales",d); st.success("Sales saved.")

def menu_page():
    st.header("Menu Quantities")
    d=day_picker("menu_date")
    cats=sql("SELECT * FROM menu_categories WHERE active=TRUE ORDER BY id",fetch=True)
    old={r["category_id"]:r["quantity"] for r in sql("SELECT category_id,quantity FROM menu_qty WHERE business_date=:d",{"d":d},True)}
    with st.form("menu"):
        vals={}
        cols=st.columns(2)
        for i,c in enumerate(cats):
            vals[c["id"]]=cols[i%2].number_input(c["name"],min_value=0,value=old.get(c["id"],0),step=1)
        ok=st.form_submit_button("Save Quantities",use_container_width=True)
    if ok:
        for c in cats:
            sql("""INSERT INTO menu_qty(business_date,category_id,quantity,updated_by)
                   VALUES(:d,:c,:q,:u)
                   ON CONFLICT(business_date,category_id) DO UPDATE SET quantity=EXCLUDED.quantity,
                   updated_at=NOW(),updated_by=EXCLUDED.updated_by""",
                {"d":d,"c":c["id"],"q":vals[c["id"]],"u":st.session_state.user["id"]})
        audit("UPSERT","menu_qty",d); st.success("Quantities saved.")

def expenses_page():
    st.header("Normal Expenses")
    d=day_picker("expense_date")
    cats=sql("SELECT * FROM expense_categories WHERE active=TRUE ORDER BY name",fetch=True)
    with st.form("expense"):
        cat=st.selectbox("Category",cats,format_func=lambda x:x["name"])
        amount=st.number_input("Amount (₹)",min_value=0.0,step=50.0)
        method=st.selectbox("Payment Method",["Cash","Bank"])
        notes=st.text_area("Notes")
        ok=st.form_submit_button("Add Expense",use_container_width=True)
    if ok and amount>0:
        sql("""INSERT INTO expenses(business_date,category_id,amount,method,notes,created_by)
               VALUES(:d,:c,:a,:m,:n,:u)""",
            {"d":d,"c":cat["id"],"a":round(amount*100),"m":method,"n":notes,"u":st.session_state.user["id"]})
        audit("CREATE","expense"); st.success("Expense added.")
    rows=sql("""SELECT e.id,c.name category,e.amount,e.method,e.notes,e.created_at
                FROM expenses e JOIN expense_categories c ON c.id=e.category_id
                WHERE e.business_date=:d AND e.deleted=FALSE ORDER BY e.id DESC""",{"d":d},True)
    if rows:
        df=pd.DataFrame(rows); df["amount"]=df["amount"]/100
        st.dataframe(df,use_container_width=True,hide_index=True)

def bulk_page():
    st.header("Bulk / Weekly Expenses")
    st.info("The full purchase affects actual cash/bank movement on its purchase Business Date. Only weekly allocations affect profit.")
    cats=sql("SELECT * FROM expense_categories WHERE active=TRUE ORDER BY name",fetch=True)
    with st.form("bulk"):
        purchase=st.date_input("Purchase Date",current_business_date())
        desc=st.text_input("Description")
        cat=st.selectbox("Category",cats,format_func=lambda x:x["name"])
        total=st.number_input("Total Purchase (₹)",min_value=0.0,step=500.0)
        method=st.selectbox("Payment Method",["Cash","Bank"])
        start=st.date_input("Allocation Start Date",purchase)
        weeks=st.number_input("Number of Weeks",min_value=1,max_value=104,value=4,step=1)
        notes=st.text_area("Notes")
        ok=st.form_submit_button("Save Bulk Expense",use_container_width=True)
    if ok and total>0:
        purchase_bd=current_business_date(datetime.combine(purchase,datetime.min.time()))
        ensure_day(purchase_bd)
        amount=round(total*100); weeks=int(weeks)
        row=sql("""INSERT INTO bulk_expenses(purchase_date,business_date,description,category_id,total,method,start_date,weeks,notes,created_by)
                   VALUES(:p,:bd,:desc,:cat,:total,:method,:start,:weeks,:notes,:u) RETURNING id""",
                {"p":purchase,"bd":purchase_bd,"desc":desc,"cat":cat["id"],"total":amount,"method":method,
                 "start":start,"weeks":weeks,"notes":notes,"u":st.session_state.user["id"]},True)[0]
        base,rem=divmod(amount,weeks)
        for i in range(weeks):
            sql("INSERT INTO bulk_alloc(bulk_id,business_date,amount) VALUES(:id,:d,:a)",
                {"id":row["id"],"d":start+timedelta(days=7*i),"a":base+(1 if i<rem else 0)})
        audit("CREATE","bulk_expense",row["id"]); st.success("Bulk expense saved.")

def rent_page():
    st.header("Daily Rent")
    d=day_picker("rent_date")
    rows=sql("SELECT * FROM rent WHERE business_date=:d",{"d":d},True)
    default=int(scalar("SELECT value FROM settings WHERE key='default_rent'",default="100000"))
    r=rows[0] if rows else {"amount":default,"paid":False,"method":"Cash","notes":""}
    with st.form("rent"):
        amount=st.number_input("Rent Amount (₹)",min_value=0.0,value=r["amount"]/100,step=100.0)
        paid=st.checkbox("Rent Paid",value=r["paid"])
        method=st.selectbox("Payment Method",["Cash","Bank"],index=0 if r["method"]!="Bank" else 1)
        notes=st.text_area("Notes",value=r["notes"] or "")
        ok=st.form_submit_button("Save Rent",use_container_width=True)
    if ok:
        sql("""INSERT INTO rent(business_date,amount,paid,method,notes,updated_by)
               VALUES(:d,:a,:p,:m,:n,:u)
               ON CONFLICT(business_date) DO UPDATE SET amount=EXCLUDED.amount,paid=EXCLUDED.paid,
               method=EXCLUDED.method,notes=EXCLUDED.notes,updated_at=NOW(),updated_by=EXCLUDED.updated_by""",
            {"d":d,"a":round(amount*100),"p":paid,"m":method,"n":notes,"u":st.session_state.user["id"]})
        audit("UPSERT","rent",d); st.success("Rent saved.")

def withdrawal_page():
    st.header("Owner Personal Withdrawal")
    d=day_picker("withdrawal_date")
    with st.form("withdrawal"):
        amount=st.number_input("Amount (₹)",min_value=0.0,step=100.0)
        method=st.selectbox("Payment Method",["Cash","Bank"])
        notes=st.text_area("Notes")
        ok=st.form_submit_button("Add Withdrawal",use_container_width=True)
    if ok and amount>0:
        sql("""INSERT INTO withdrawals(business_date,amount,method,notes,created_by)
               VALUES(:d,:a,:m,:n,:u)""",
            {"d":d,"a":round(amount*100),"m":method,"n":notes,"u":st.session_state.user["id"]})
        audit("CREATE","withdrawal"); st.success("Withdrawal added.")

def business_days_page():
    st.header("Business Days / Holidays / Missed Days")
    d=st.date_input("Date",current_business_date(),key="business_day")
    ensure_day(d)
    r=sql("SELECT * FROM business_days WHERE business_date=:d",{"d":d},True)[0]
    with st.form("businessday"):
        status=st.selectbox("Status",["OPEN","CLOSED","HOLIDAY"],index=["OPEN","CLOSED","HOLIDAY"].index(r["status"]))
        reason=st.text_input("Holiday reason",value=r["holiday_reason"] or "")
        notes=st.text_area("Notes",value=r["notes"] or "")
        ok=st.form_submit_button("Save Day")
    if ok:
        sql("UPDATE business_days SET status=:s,holiday_reason=:r,notes=:n WHERE business_date=:d",
            {"s":status,"r":reason,"n":notes,"d":d})
        audit("UPDATE","business_day",d); st.success("Updated.")
    st.subheader("Recent business days")
    rows=sql("SELECT business_date,status,holiday_reason FROM business_days ORDER BY business_date DESC LIMIT 90",fetch=True)
    st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)

def report_page(period):
    st.header(f"{period} Report")
    if period=="Daily":
        d=day_picker("daily_report")
        t=totals(d)
        cols=st.columns(4)
        for col,label,key in zip(cols,["Sales","Expenses + Allocations","Profit Before Rent","Profit After Rent"],["sales","normal","before","after"]):
            val=t[key] if key in t else t["normal"]+t["alloc"]
            col.metric(label,money(val))
        st.json({k:(money(v) if isinstance(v,int) else v) for k,v in t.items()})
        return
    if period=="Weekly":
        start=st.date_input("Week Start",current_business_date(),key="week_report")
        end=start+timedelta(days=7)
    else:
        year=st.number_input("Year",2020,2100,date.today().year,key="month_year")
        month=st.number_input("Month",1,12,date.today().month,key="month_num")
        start=date(int(year),int(month),1)
        end=date(int(year)+1,1,1) if int(month)==12 else date(int(year),int(month)+1,1)
    dates=[start+timedelta(days=i) for i in range((end-start).days)]
    rows=[]
    for d in dates:
        t=totals(d)
        menu=sql("""SELECT c.name,COALESCE(q.quantity,0) quantity FROM menu_categories c
                    LEFT JOIN menu_qty q ON q.category_id=c.id AND q.business_date=:d
                    WHERE c.active=TRUE ORDER BY c.id""",{"d":d},True)
        m={x["name"]:x["quantity"] for x in menu}
        status=scalar("SELECT status FROM business_days WHERE business_date=:d",{"d":d},default="NOT ENTERED")
        rows.append({"Business Date":d,"Status":status,"Sales":t["sales"]/100,"Normal Expenses":t["normal"]/100,
                     "Bulk Allocation":t["alloc"]/100,"Profit Before Rent":t["before"]/100,
                     "Rent Paid":(t["rent"] if t["rent_paid"] else 0)/100,"Profit After Rent":t["after"]/100,
                     "Withdrawals":t["withdrawal"]/100,"Momos":m.get("Momos",0),"Pasta":m.get("Pasta",0),
                     "Fries":m.get("Fries",0),"Loaded Fries":m.get("Loaded Fries",0)})
    df=pd.DataFrame(rows)
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.download_button("Download Report CSV",df.to_csv(index=False).encode(),"yours_momos_report.csv","text/csv")
    if not df.empty:
        for col in ["Sales","Normal Expenses","Bulk Allocation","Profit Before Rent","Rent Paid","Profit After Rent","Withdrawals"]:
            st.metric(col,f"₹{df[col].sum():,.2f}")

def settings_page():
    if st.session_state.user["role"]!="OWNER":
        st.warning("Owner access required.")
        return
    st.header("Settings")
    cutoff=scalar("SELECT value FROM settings WHERE key='business_cutoff'",default="04:00")
    opening=scalar("SELECT value FROM settings WHERE key='shop_open'",default="18:00")
    default=int(scalar("SELECT value FROM settings WHERE key='default_rent'",default="100000"))
    st.write(f"Business date cutoff: **{cutoff}**")
    st.write(f"Shop opening time: **{opening}**")
    with st.form("settings"):
        rent=st.number_input("Default Daily Rent (₹)",min_value=0.0,value=default/100,step=100.0)
        ok=st.form_submit_button("Save Settings")
    if ok:
        sql("UPDATE settings SET value=:v WHERE key='default_rent'",{"v":str(round(rent*100))})
        audit("UPDATE","settings","default_rent"); st.success("Saved.")
    st.subheader("User Management")
    users=sql("SELECT id,username,name,role,active,created_at FROM users ORDER BY id",fetch=True)
    st.dataframe(pd.DataFrame(users),use_container_width=True,hide_index=True)
    with st.form("newuser"):
        name=st.text_input("Name"); username=st.text_input("Username"); password=st.text_input("Password",type="password")
        role=st.selectbox("Role",["STAFF","OWNER"]); ok=st.form_submit_button("Create User")
    if ok:
        try:
            sql("INSERT INTO users(username,name,password_hash,role) VALUES(:u,:n,:h,:r)",
                {"u":username,"n":name,"h":bcrypt.hashpw(password.encode(),bcrypt.gensalt()).decode(),"r":role})
            audit("CREATE","user",username); st.success("User created.")
        except Exception as e: st.error(f"Could not create user: {e}")
    st.subheader("Database")
    st.success("Data is stored in the remote PostgreSQL database, not in the Streamlit app filesystem.")
    st.caption("Use your database provider's backup/point-in-time recovery for production backups.")

def main():
    init_db()
    if "user" not in st.session_state:
        login(); return
    st.sidebar.title("🥟 Yours Momos")
    st.sidebar.write(f"**{st.session_state.user['name']}** · {st.session_state.user['role']}")
    choices=["Dashboard","Daily Sales","Menu Quantities","Expenses","Bulk Expenses","Daily Rent","Owner Withdrawal",
             "Business Days","Daily Report","Weekly Report","Monthly Report","Settings"]
    page=st.sidebar.radio("Navigation",choices)
    if st.sidebar.button("Logout"):
        audit("LOGOUT"); del st.session_state.user; st.rerun()
    funcs={"Dashboard":dashboard,"Daily Sales":sales_page,"Menu Quantities":menu_page,"Expenses":expenses_page,
           "Bulk Expenses":bulk_page,"Daily Rent":rent_page,"Owner Withdrawal":withdrawal_page,
           "Business Days":business_days_page,"Daily Report":lambda:report_page("Daily"),
           "Weekly Report":lambda:report_page("Weekly"),"Monthly Report":lambda:report_page("Monthly"),
           "Settings":settings_page}
    funcs[page]()

if __name__=="__main__":
    main()
