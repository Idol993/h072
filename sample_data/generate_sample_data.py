import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

np.random.seed(42)

categories = ["电子产品", "服装", "食品", "家居", "美妆"]
subcategories = {
    "电子产品": ["手机", "电脑", "配件"],
    "服装": ["男装", "女装", "童装"],
    "食品": ["零食", "饮料", "生鲜"],
    "家居": ["家具", "厨具", "床品"],
    "美妆": ["护肤", "彩妆", "香水"]
}
regions = ["华东", "华南", "华北", "西南", "华中", "西北", "东北"]
channels = ["线上官网", "天猫", "京东", "拼多多", "抖音", "线下门店"]
statuses = ["paid", "cancelled", "refunded"]

start_date = datetime.now() - timedelta(days=90)
end_date = datetime.now()

records = []
order_id = 1

current_date = start_date
while current_date <= end_date:
    if current_date.weekday() >= 5:
        base_orders = np.random.randint(80, 120)
    else:
        base_orders = np.random.randint(50, 80)

    for _ in range(base_orders):
        category = np.random.choice(categories)
        subcat = np.random.choice(subcategories[category])
        region = np.random.choice(regions)
        channel = np.random.choice(channels, p=[0.25, 0.25, 0.2, 0.15, 0.1, 0.05])
        status = np.random.choice(statuses, p=[0.85, 0.1, 0.05])

        base_amount = {
            "电子产品": np.random.uniform(500, 5000),
            "服装": np.random.uniform(50, 500),
            "食品": np.random.uniform(20, 200),
            "家居": np.random.uniform(100, 3000),
            "美妆": np.random.uniform(30, 800)
        }[category]

        hour = np.random.randint(9, 23)
        minute = np.random.randint(0, 60)
        order_datetime = current_date.replace(hour=hour, minute=minute)

        records.append({
            "order_id": order_id,
            "order_date": order_datetime,
            "category": category,
            "subcategory": subcat,
            "region": region,
            "channel": channel,
            "order_amount": round(base_amount, 2),
            "status": status,
            "updated_at": datetime.now()
        })
        order_id += 1

    if current_date.weekday() == 0:
        for category in ["电子产品", "服装"]:
            subcat = np.random.choice(subcategories[category])
            region = np.random.choice(["华东", "华南"])
            channel = "天猫"
            for _ in range(np.random.randint(20, 40)):
                base_amount = {
                    "电子产品": np.random.uniform(500, 5000),
                    "服装": np.random.uniform(50, 500)
                }[category]

                hour = np.random.randint(9, 23)
                minute = np.random.randint(0, 60)
                order_datetime = current_date.replace(hour=hour, minute=minute)

                records.append({
                    "order_id": order_id,
                    "order_date": order_datetime,
                    "category": category,
                    "subcategory": subcat,
                    "region": region,
                    "channel": channel,
                    "order_amount": round(base_amount, 2),
                    "status": "paid",
                    "updated_at": datetime.now()
                })
                order_id += 1

    if current_date.day == 15:
        for region in ["东北", "西北"]:
            for _ in range(np.random.randint(5, 15)):
                category = np.random.choice(["食品", "家居"])
                subcat = np.random.choice(subcategories[category])
                channel = np.random.choice(["拼多多", "抖音"])
                base_amount = np.random.uniform(50, 300)

                hour = np.random.randint(9, 23)
                minute = np.random.randint(0, 60)
                order_datetime = current_date.replace(hour=hour, minute=minute)

                records.append({
                    "order_id": order_id,
                    "order_date": order_datetime,
                    "category": category,
                    "subcategory": subcat,
                    "region": region,
                    "channel": channel,
                    "order_amount": round(base_amount, 2),
                    "status": "paid",
                    "updated_at": datetime.now()
                })
                order_id += 1

    current_date += timedelta(days=1)

df = pd.DataFrame(records)
output_path = os.path.join(os.path.dirname(__file__), "orders.csv")
df.to_csv(output_path, index=False, encoding="utf-8-sig")

print(f"Generated {len(df)} orders")
print(f"Date range: {df['order_date'].min()} to {df['order_date'].max()}")
print(f"Paid orders: {len(df[df['status'] == 'paid'])}")
print(f"Total GMV: ¥{df[df['status'] == 'paid']['order_amount'].sum():,.2f}")
print(f"Saved to: {output_path}")
