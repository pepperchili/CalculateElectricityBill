import sqlite3
from flask import Flask, render_template, request, redirect, url_for, flash
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_key_for_demo'
DB_NAME = 'electricity.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    with open('schema.sql') as f:
        conn.executescript(f.read())
    conn.close()

def calculate_tier_cost(usage, month_str):
    """
    Calculates cost based on "Split Tiers" (档位/2) method.
    Returns (cost, breakdown_text)
    """
    try:
        month_obj = datetime.strptime(month_str, '%Y-%m')
        month = month_obj.month
    except:
        month = 1 # Default to non-summer if parsing fails

    # Determine Season
    # Summer: May (5) to Oct (10)
    is_summer = 5 <= month <= 10
    
    # Tier Limits (Halved for single user share)
    if is_summer:
        t1_limit = 260 / 2  # 130
        t2_limit = 600 / 2  # 300
        season_name = "夏季标准(5-10月)"
    else:
        t1_limit = 200 / 2  # 100
        t2_limit = 400 / 2  # 200
        season_name = "非夏季标准(11-4月)"

    # Prices
    p1 = 0.58886875
    p2 = 0.63886875
    p3 = 0.88886875

    cost = 0
    breakdown = []
    tier_costs = []
    breakdown.append(f"季节: {season_name}, 档位减半执行")

    remaining = usage
    
    # Tier 1
    t1_usage = min(remaining, t1_limit)
    t1_cost = t1_usage * p1
    cost += t1_cost
    tier_costs.append(t1_cost)
    breakdown.append(f"第一档(0-{t1_limit}): {t1_usage:.2f}度 × {p1} = {t1_cost:.2f}元")
    remaining -= t1_usage

    # Tier 2
    if remaining > 0:
        # The span of tier 2 is (t2_limit - t1_limit)
        t2_span = t2_limit - t1_limit
        t2_usage = min(remaining, t2_span)
        t2_cost = t2_usage * p2
        cost += t2_cost
        tier_costs.append(t2_cost)
        breakdown.append(f"第二档({t1_limit}-{t2_limit}): {t2_usage:.2f}度 × {p2} = {t2_cost:.2f}元")
        remaining -= t2_usage

    # Tier 3
    if remaining > 0:
        t3_cost = remaining * p3
        cost += t3_cost
        tier_costs.append(t3_cost)
        breakdown.append(f"第三档(>{t2_limit}): {remaining:.2f}度 × {p3} = {t3_cost:.2f}元")

    return cost, "\n".join(breakdown), tier_costs

@app.route('/', methods=('GET', 'POST'))
def index():
    conn = get_db_connection()
    
    if request.method == 'POST':
        billing_month = request.form['billing_month']
        meter_reading = float(request.form['meter_reading'])
        total_bill = float(request.form['total_bill'])
        
        # Get previous reading
        last_record = conn.execute('SELECT * FROM records ORDER BY billing_month DESC, id DESC LIMIT 1').fetchone()
        
        if last_record:
            prev_reading = last_record['meter_reading']
            prev_month_str = last_record['billing_month']
            usage = meter_reading - prev_reading
            
            # Calculate month gap
            try:
                curr_date = datetime.strptime(billing_month, '%Y-%m')
                prev_date = datetime.strptime(prev_month_str, '%Y-%m')
                # Calculate difference in months
                months_diff = (curr_date.year - prev_date.year) * 12 + (curr_date.month - prev_date.month)
                
                if months_diff < 1:
                    months_diff = 1 # Fallback if same month or error
            except:
                months_diff = 1
        else:
            # First entry
            usage = 0
            months_diff = 1
            
        if usage < 0:
            flash("错误：当前读数不能小于上月读数！")
        else:
            # Calculate User Cost
            if usage == 0:
                user_cost = 0
                neighbor_cost = 0
                note = "初始读数，无用量"
            else:
                # Average usage per month to avoid unfair tier jumping
                avg_usage = usage / months_diff
                
                # Calculate cost for ONE month based on average usage
                # Note: This assumes the season standard of the CURRENT month applies to the whole period
                # or we could try to be fancy and calculate per month, but user asked for "usage/2" logic.
                monthly_cost, monthly_note, tier_costs = calculate_tier_cost(avg_usage, billing_month)
                
                user_cost = monthly_cost * months_diff
                neighbor_cost = total_bill - user_cost
                
                if months_diff > 1:
                    note = f"跨度 {months_diff} 个月 (上次抄表: {prev_month_str})\n"
                    note += f"总用量 {usage:.2f} ÷ {months_diff} = 平均每月 {avg_usage:.2f} 度\n"
                    note += "-" * 20 + "\n"
                    note += "506电费计算:\n"
                    note += f"单月计算:\n{monthly_note}\n"
                    note += "-" * 20 + "\n"
                    note += f"506应付: {monthly_cost:.2f}元 × {months_diff}个月 = {user_cost:.2f}元\n"
                    note += f"507应付: {total_bill:.2f} - {user_cost:.2f} = {neighbor_cost:.2f}元\n"
                else:
                    note = "506电费计算:\n"
                    note += monthly_note
                    note += "\n" + "-" * 20 + "\n"
                    cost_formula = " + ".join([f"{c:.2f}" for c in tier_costs])
                    if len(tier_costs) > 1:
                        note += f"506应付: {cost_formula} = {user_cost:.2f}元\n"
                    else:
                        note += f"506应付: {user_cost:.2f}元\n"
                    note += f"507应付: {total_bill:.2f} - {user_cost:.2f} = {neighbor_cost:.2f}元\n"

            conn.execute('INSERT INTO records (billing_month, meter_reading, total_bill, usage, user_cost, neighbor_cost, calculation_note) VALUES (?, ?, ?, ?, ?, ?, ?)',
                         (billing_month, meter_reading, total_bill, usage, user_cost, neighbor_cost, note))
            conn.commit()
            return redirect(url_for('index'))

    records_data = conn.execute('SELECT * FROM records ORDER BY billing_month DESC, id DESC').fetchall()
    
    # Convert to list of dicts to modify
    records = []
    for row in records_data:
        r = dict(row)
        # Calculate previous reading: current reading - usage
        # Use round to avoid floating point errors
        r['prev_reading'] = round(r['meter_reading'] - r['usage'], 2)
        records.append(r)
    
    # Find the latest reading to display as "Previous Reading" for the form
    latest = records[0] if records else None
    prev_reading_display = latest['meter_reading'] if latest else 0
    
    conn.close()
    return render_template('index.html', records=records, prev_reading=prev_reading_display)

@app.route('/delete/<int:id>', methods=('POST',))
def delete(id):
    conn = get_db_connection()
    conn.execute('DELETE FROM records WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/init_db')
def initialize():
    init_db()
    return "Database initialized!"

if __name__ == '__main__':
    # Auto-init DB if not exists
    import os
    if not os.path.exists(DB_NAME):
        init_db()
    app.run(host='0.0.0.0', debug=True, port=5001)
