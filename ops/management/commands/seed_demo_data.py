import random
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import Role, User
from ops.models import Branch, Category, Expense, InstallationJob, Lead, Payslip, Product, Purchase, Sale, Supplier, Technician, TodoItem


def month_start(d, months_back):
    month = d.month - months_back
    year = d.year
    while month <= 0:
        month += 12
        year -= 1
    return d.replace(year=year, month=month, day=1)


def random_day_in_month(today, months_back, max_offset=26):
    """A random date within that month, never later than `today`."""
    start = month_start(today, months_back)
    cap = max_offset if months_back > 0 else min(max_offset, (today - start).days)
    return start + timedelta(days=random.randint(0, max(cap, 0)))

DSM_AREAS = [
    "Mikocheni", "Kariakoo", "Tegeta", "Masaki", "Sinza",
    "Kinondoni", "Ubungo", "Mbezi Beach", "Kigamboni", "Upanga",
]

CUSTOMER_NAMES = [
    "Amina Hassan", "John Mwakalinga", "Neema Kessy", "Peter Chacha", "Zainab Iddi",
    "Daudi Mrema", "Halima Suleiman", "Victor Komba", "Rehema Ally", "Michael Temba",
    "Salma Juma", "Godfrey Massawe", "Fatima Rashid", "Elias Ngowi", "Winnie Mushi",
    "Ibrahim Kilonzo", "Grace Materu", "Said Mfaume",
]


class Command(BaseCommand):
    help = "Seed the ops dashboard with realistic RK General Traders demo data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-seed even if installation jobs already exist (wipes existing ops data).",
        )

    def handle(self, *args, **options):
        if not options["force"] and InstallationJob.objects.exists():
            self.stdout.write("Ops data already present, skipping (use --force to re-seed).")
            return

        random.seed(42)
        today = timezone.localdate()

        self.stdout.write("Clearing existing ops data...")
        Sale.objects.all().delete()
        Expense.objects.all().delete()
        Purchase.objects.all().delete()
        Product.objects.all().delete()
        Category.objects.all().delete()
        Supplier.objects.all().delete()
        Payslip.objects.all().delete()
        TodoItem.objects.all().delete()
        InstallationJob.objects.all().delete()
        Lead.objects.all().delete()
        Technician.objects.all().delete()
        Branch.objects.all().delete()

        branches = [
            Branch.objects.create(
                name="Kariakoo Shop", location="Kariakoo, Dar es Salaam", phone="+255 754 000 100",
            ),
            Branch.objects.create(
                name="Mikocheni Shop", location="Mikocheni, Dar es Salaam", phone="+255 754 000 200",
            ),
        ]
        self.stdout.write(self.style.SUCCESS(f"Created {len(branches)} branches"))

        role_defs = [
            ("manager", "Manager", ["dashboard", "jobs", "leads", "customers", "staff", "sales", "purchases", "inventory", "suppliers", "categories"]),
            ("accountant", "Accountant", ["dashboard", "payroll", "finance", "sales", "purchases", "inventory", "expenses", "suppliers", "categories"]),
            ("sales", "Sales", ["dashboard", "jobs", "leads", "customers", "sales", "inventory"]),
        ]
        for key, name, modules in role_defs:
            Role.objects.update_or_create(key=key, defaults={"name": name, "modules": modules})
        self.stdout.write(self.style.SUCCESS(f"Created {len(role_defs)} roles"))

        DEMO_PASSWORD = "Demo@12345"
        demo_account_specs = [
            ("admin.rogers", "Rogers", "Kamala", "rogers.kamala@rkgeneraltraders.co.tz", User.ADMIN, None),
            ("manager.emmanuel", "Emmanuel", "Shirima", "emmanuel.shirima@rkgeneraltraders.co.tz", "manager", branches[1]),
            ("accountant.grace", "Grace", "Mmbaga", "grace.mmbaga@rkgeneraltraders.co.tz", "accountant", branches[0]),
            ("sales.baraka", "Baraka", "Mushi", "baraka.mushi@rkgeneraltraders.co.tz", "sales", branches[1]),
            ("sales.fatuma", "Fatuma", "Juma", "fatuma.juma@rkgeneraltraders.co.tz", "sales", branches[0]),
        ]
        demo_accounts = []
        for username, first_name, last_name, email, role, branch in demo_account_specs:
            account, _ = User.objects.update_or_create(
                username=username,
                defaults={
                    "first_name": first_name,
                    "last_name": last_name,
                    "email": email,
                    "role": role,
                    "branch": branch,
                    "is_active": True,
                },
            )
            account.set_password(DEMO_PASSWORD)
            account.save()
            demo_accounts.append(account)
        self.stdout.write(self.style.SUCCESS(
            f"Created {len(demo_accounts)} demo login accounts (password: {DEMO_PASSWORD})"
        ))

        # Every non-admin/superadmin account above just auto-created a linked
        # Staff Directory entry (see ops/signals.py). Flesh those out with
        # realistic job titles and salaries rather than duplicating the people
        # as separate, unlinked technicians.
        technician_overrides = {
            "manager.emmanuel": {"role": "Network Engineer", "monthly_salary": 950_000, "tint": 4},
            "accountant.grace": {"role": "Accountant", "monthly_salary": 850_000, "tint": 5},
            "sales.baraka": {"role": "Field Technician", "monthly_salary": 650_000, "tint": 2},
            "sales.fatuma": {"role": "Field Technician", "monthly_salary": 650_000, "tint": 3},
        }
        linked_technicians = []
        for account in demo_accounts:
            overrides = technician_overrides.get(account.username)
            if not overrides:
                continue
            tech = account.technician_profile
            for field, value in overrides.items():
                setattr(tech, field, value)
            tech.save()
            linked_technicians.append(tech)

        extra_technicians = [
            Technician.objects.create(
                name="Peter Mnyika", role="Field Technician", access_role="sales",
                email="peter.mnyika@rkgeneraltraders.co.tz", phone="+255 700 000 006", tint=6,
                monthly_salary=600_000,
            ),
            Technician.objects.create(
                name="Joseph Kileo", role="Customer Support", access_role="",
                email="joseph.kileo@rkgeneraltraders.co.tz", phone="+255 700 000 007", tint=1,
                monthly_salary=550_000,
            ),
        ]
        technicians = linked_technicians + extra_technicians
        self.stdout.write(self.style.SUCCESS(f"Staff directory has {len(technicians)} entries ({len(linked_technicians)} linked to a login account)"))
        self.stdout.write(self.style.SUCCESS(f"Created {len(technicians)} technicians"))

        interests = [c[0] for c in Lead.Interest.choices]
        sources = [c[0] for c in Lead.Source.choices]
        lead_statuses = (
            [Lead.Status.NEW] * 4
            + [Lead.Status.CONTACTED] * 3
            + [Lead.Status.QUOTED] * 3
            + [Lead.Status.CONVERTED] * 6
            + [Lead.Status.LOST] * 4
        )
        random.shuffle(lead_statuses)

        leads = []
        for i, status in enumerate(lead_statuses):
            name = random.choice(CUSTOMER_NAMES)
            lead = Lead.objects.create(
                branch=random.choice(branches),
                name=name,
                phone=f"+255 7{random.randint(10,99)} {random.randint(100,999)} {random.randint(100,999)}",
                email=f"{name.split()[0].lower()}{i}@example.com",
                location=random.choice(DSM_AREAS),
                interest=random.choice(interests),
                source=random.choice(sources),
                status=status,
                notes="",
            )
            leads.append(lead)
        self.stdout.write(self.style.SUCCESS(f"Created {len(leads)} leads"))

        job_titles = {
            InstallationJob.Category.FIBER: "Fiber installation",
            InstallationJob.Category.ROUTER: "Router setup",
            InstallationJob.Category.EXTENDER: "Wi-Fi extender install",
            InstallationJob.Category.MIKROTIK: "Mikrotik voucher setup",
            InstallationJob.Category.ACCESS_POINT: "Access point install",
            InstallationJob.Category.ONU: "Fiber ONU/ONT swap",
            InstallationJob.Category.UPS: "UPS backup install",
            InstallationJob.Category.SUPPORT: "Maintenance visit",
        }
        job_status_plan = (
            [InstallationJob.Status.NOT_STARTED] * 4
            + [InstallationJob.Status.IN_PROGRESS] * 5
            + [InstallationJob.Status.REVIEW] * 2
            + [InstallationJob.Status.ON_HOLD] * 2
            + [InstallationJob.Status.CANCELLED] * 2
            + [InstallationJob.Status.DONE] * 5
        )
        random.shuffle(job_status_plan)
        priorities = [c[0] for c in InstallationJob.Priority.choices]

        jobs = []
        for i, status in enumerate(job_status_plan):
            category = random.choice(list(job_titles.keys()))
            customer = random.choice(CUSTOMER_NAMES)
            area = random.choice(DSM_AREAS)
            job = InstallationJob.objects.create(
                branch=random.choice(branches),
                title=f"{job_titles[category]} — {area}",
                customer_name=customer,
                location=area,
                category=category,
                status=status,
                priority=random.choice(priorities),
                assigned_to=random.choice(technicians),
                start_date=today + timedelta(days=random.randint(-10, 12)),
            )
            jobs.append(job)
        self.stdout.write(self.style.SUCCESS(f"Created {len(jobs)} installation jobs"))

        todo_specs = [
            ("Confirm fiber ONU delivery for Mikocheni job", "Check with the supplier that the ONU unit arrives before Friday's install.", 2, False),
            ("Call customer about Wi-Fi extender quote", "Follow up on the quote sent Tuesday — no response yet.", 1, False),
            ("Restock Mikrotik voucher cards", "Print and prepare 200 more voucher cards for hotspot clients.", 4, False),
            ("Submit weekly installation report", "Summarize completed jobs and pending customer follow-ups.", 0, True),
            ("Inspect rooftop dish at Tegeta site", "Signal has been unstable — check alignment and cabling.", 3, False),
            ("Onboard new field technician", "Walk through safety gear checklist and install procedures.", 5, False),
            ("Update customer contact list", "Merge new leads from this week into the shared contact sheet.", 1, True),
            ("Review UPS stock levels", "Confirm enough units in stock for two upcoming power-backup jobs.", 6, False),
        ]
        todos = []
        for title, desc, days, done in todo_specs:
            todos.append(
                TodoItem.objects.create(
                    title=title,
                    description=desc,
                    due_date=today + timedelta(days=days),
                    assigned_to=random.choice(technicians),
                    done=done,
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Created {len(todos)} todo items"))

        payslips = []
        for months_back in (2, 1, 0):
            period = month_start(today, months_back)
            for tech in technicians:
                allowance = random.choice([40_000, 50_000, 60_000, 75_000, 80_000])
                deduction = round(float(tech.monthly_salary) * random.uniform(0.06, 0.1), -3)
                is_current_month = months_back == 0
                status = Payslip.Status.DRAFT if is_current_month else Payslip.Status.PAID
                paid_date = None if is_current_month else (period.replace(day=28))
                payslips.append(
                    Payslip.objects.create(
                        technician=tech,
                        period=period,
                        base_salary=tech.monthly_salary,
                        allowances=allowance,
                        deductions=deduction,
                        status=status,
                        paid_date=paid_date,
                    )
                )
        self.stdout.write(self.style.SUCCESS(f"Created {len(payslips)} payslips"))

        suppliers = [
            Supplier.objects.create(
                name="TP-Link Tanzania Distributors", contact_person="Hassan Mrisho",
                phone="+255 754 100 200", email="sales@tplink-tz.example.com",
                notes="Primary source for routers and Wi-Fi extenders.",
            ),
            Supplier.objects.create(
                name="MikroTik East Africa", contact_person="Elizabeth Komba",
                phone="+255 754 200 300", email="orders@mikrotik-ea.example.com",
                notes="RouterBoard hardware and licensing.",
            ),
            Supplier.objects.create(
                name="Vodacom Business Wholesale", contact_person="Daniel Nyerere",
                phone="+255 754 300 400", email="wholesale@vodacom.example.co.tz",
                notes="Fiber ONU/ONT units and bulk data capacity.",
            ),
            Supplier.objects.create(
                name="Dar Cables & Networking Supplies", contact_person="Peter Massawe",
                phone="+255 754 400 500", email="info@darcables.example.com",
                notes="Cabling, connectors, UPS units, and general accessories.",
            ),
        ]
        self.stdout.write(self.style.SUCCESS(f"Created {len(suppliers)} suppliers"))

        category_defs = [
            ("router", "Router"),
            ("wifi_extender", "Wi-Fi Extender"),
            ("mikrotik", "Mikrotik"),
            ("access_point", "Access Point"),
            ("fiber_onu_ont", "Fiber ONU/ONT"),
            ("power_backup", "Power Backup (UPS)"),
            ("cable", "Cable & Accessories"),
            ("other", "Other"),
        ]
        categories = {key: Category.objects.create(name=name) for key, name in category_defs}
        self.stdout.write(self.style.SUCCESS(f"Created {len(categories)} categories"))

        product_catalog = [
            ("router", "Router", "pcs", 5),
            ("wifi_extender", "Wi-Fi Extender", "pcs", 5),
            ("mikrotik", "MikroTik RouterBoard", "pcs", 3),
            ("access_point", "Access Point", "pcs", 3),
            ("fiber_onu_ont", "Fiber ONU/ONT", "pcs", 5),
            ("power_backup", "UPS Backup Unit", "pcs", 3),
            ("cable", "Cat6 Cable Roll", "roll", 10),
        ]
        products_by_branch_key = {}
        for branch in branches:
            for key, name, unit, reorder_level in product_catalog:
                product = Product.objects.create(
                    branch=branch, name=name, category=categories[key], unit=unit,
                    reorder_level=reorder_level, quantity_on_hand=0,
                )
                products_by_branch_key[(branch.id, key)] = product
        self.stdout.write(self.style.SUCCESS(f"Created {len(products_by_branch_key)} catalog products across {len(branches)} branches"))

        purchase_specs = {
            "router": ("Router units", suppliers[0], (120_000, 180_000)),
            "wifi_extender": ("Wi-Fi extender units", suppliers[0], (60_000, 90_000)),
            "mikrotik": ("MikroTik RouterBoard hAP units", suppliers[1], (250_000, 400_000)),
            "access_point": ("Access point units", suppliers[1], (200_000, 320_000)),
            "fiber_onu_ont": ("Fiber ONU/ONT units", suppliers[2], (90_000, 140_000)),
            "power_backup": ("UPS backup units", suppliers[3], (180_000, 350_000)),
            "cable": ("Cat6 cable rolls & connectors", suppliers[3], (5_000, 20_000)),
        }
        purchase_status_plan = (
            [Purchase.Status.RECEIVED] * 11 + [Purchase.Status.ORDERED] * 4 + [Purchase.Status.CANCELLED] * 2
        )
        random.shuffle(purchase_status_plan)

        purchases = []
        for i, status in enumerate(purchase_status_plan):
            branch = random.choice(branches)
            key = random.choice(list(purchase_specs.keys()))
            label, supplier, (low, high) = purchase_specs[key]
            months_back = random.choice([0, 0, 1, 2])
            quantity = random.randint(20, 60) if key == "cable" else random.randint(2, 12)
            purchases.append(
                Purchase.objects.create(
                    branch=branch,
                    supplier=supplier,
                    product=products_by_branch_key.get((branch.id, key)),
                    item_name=label,
                    category=categories[key],
                    quantity=quantity,
                    unit_cost=random.randint(low // 1000, high // 1000) * 1000,
                    status=status,
                    purchase_date=random_day_in_month(today, months_back),
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Created {len(purchases)} purchases"))

        expense_specs = [
            (Expense.Category.RENT, "Office & warehouse rent", (800_000, 800_000)),
            (Expense.Category.UTILITIES, "Electricity (LUKU) top-up", (60_000, 120_000)),
            (Expense.Category.UTILITIES, "Office internet & airtime", (40_000, 70_000)),
            (Expense.Category.FUEL_TRANSPORT, "Fuel for install van", (30_000, 80_000)),
            (Expense.Category.FUEL_TRANSPORT, "Bajaji fare to Mikocheni site", (10_000, 25_000)),
            (Expense.Category.MARKETING, "Facebook & Instagram ads", (50_000, 150_000)),
            (Expense.Category.MARKETING, "Printed flyers for Kariakoo shop", (30_000, 60_000)),
            (Expense.Category.MAINTENANCE, "Crimping tool & tester repair", (20_000, 45_000)),
            (Expense.Category.MAINTENANCE, "Install van service", (80_000, 180_000)),
            (Expense.Category.OFFICE_SUPPLIES, "Printer paper & ink", (15_000, 35_000)),
            (Expense.Category.OFFICE_SUPPLIES, "Voucher card printing", (25_000, 60_000)),
            (Expense.Category.OTHER, "Bank transaction fees", (5_000, 15_000)),
        ]
        payment_methods = [c[0] for c in Expense.PaymentMethod.choices]

        expenses = []
        for months_back in (2, 1, 0):
            for category, desc, (low, high) in expense_specs:
                if random.random() < 0.25 and category != Expense.Category.RENT:
                    continue  # not every expense repeats every month
                expenses.append(
                    Expense.objects.create(
                        branch=random.choice(branches),
                        category=category,
                        description=desc,
                        amount=random.randint(low // 1000, high // 1000) * 1000,
                        expense_date=random_day_in_month(today, months_back),
                        payment_method=random.choice(payment_methods),
                        recorded_by=random.choice(technicians),
                    )
                )
        self.stdout.write(self.style.SUCCESS(f"Created {len(expenses)} expenses"))

        service_prices = {
            Sale.Category.FIBER: (200_000, 350_000),
            Sale.Category.ROUTER: (60_000, 100_000),
            Sale.Category.EXTENDER: (50_000, 90_000),
            Sale.Category.MIKROTIK: (120_000, 200_000),
            Sale.Category.ACCESS_POINT: (100_000, 180_000),
            Sale.Category.ONU: (70_000, 130_000),
            Sale.Category.UPS: (60_000, 110_000),
            Sale.Category.SUPPORT: (30_000, 60_000),
        }
        payment_status_for_job_sale = (
            [Sale.PaymentStatus.PAID] * 4 + [Sale.PaymentStatus.PARTIAL] * 1
        )

        sales = []
        done_jobs = [j for j in jobs if j.status == InstallationJob.Status.DONE]
        for job in done_jobs:
            low, high = service_prices.get(job.category, (50_000, 100_000))
            unit_price = random.randint(low // 1000, high // 1000) * 1000
            status = random.choice(payment_status_for_job_sale)
            amount_paid = unit_price if status == Sale.PaymentStatus.PAID else round(unit_price * 0.5, -3)
            sales.append(
                Sale.objects.create(
                    branch=job.branch,
                    customer_name=job.customer_name,
                    job=job,
                    category=job.category,
                    description=job.title,
                    quantity=1,
                    unit_price=unit_price,
                    amount_paid=amount_paid,
                    payment_status=status,
                    payment_method=random.choice(payment_methods),
                    sale_date=job.start_date or today,
                )
            )

        product_specs = [
            (Sale.Category.PRODUCT, "Router (retail)", (220_000, 320_000), "router"),
            (Sale.Category.PRODUCT, "Wi-Fi Extender (retail)", (110_000, 160_000), "wifi_extender"),
            (Sale.Category.PRODUCT, "MikroTik RouterBoard (retail)", (380_000, 550_000), "mikrotik"),
            (Sale.Category.PRODUCT, "Access Point (retail)", (300_000, 420_000), "access_point"),
            (Sale.Category.PRODUCT, "Fiber ONU/ONT (retail)", (140_000, 200_000), "fiber_onu_ont"),
            (Sale.Category.PRODUCT, "UPS Backup Unit (retail)", (280_000, 450_000), "power_backup"),
        ]
        sale_status_plan = (
            [Sale.PaymentStatus.PAID] * 12 + [Sale.PaymentStatus.PARTIAL] * 4 + [Sale.PaymentStatus.UNPAID] * 3
        )
        random.shuffle(sale_status_plan)

        for i, status in enumerate(sale_status_plan):
            branch = random.choice(branches)
            category, desc, (low, high), product_key = random.choice(product_specs)
            months_back = random.choice([0, 0, 1, 2])
            quantity = random.randint(1, 3)
            unit_price = random.randint(low // 1000, high // 1000) * 1000
            total = unit_price * quantity
            if status == Sale.PaymentStatus.PAID:
                amount_paid = total
            elif status == Sale.PaymentStatus.PARTIAL:
                amount_paid = round(total * random.uniform(0.3, 0.7), -3)
            else:
                amount_paid = 0
            sales.append(
                Sale.objects.create(
                    branch=branch,
                    customer_name=random.choice(CUSTOMER_NAMES),
                    product=products_by_branch_key.get((branch.id, product_key)),
                    category=category,
                    description=desc,
                    quantity=quantity,
                    unit_price=unit_price,
                    amount_paid=amount_paid,
                    payment_status=status,
                    payment_method=random.choice(payment_methods),
                    sale_date=random_day_in_month(today, months_back),
                )
            )
        self.stdout.write(self.style.SUCCESS(f"Created {len(sales)} sales"))

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
