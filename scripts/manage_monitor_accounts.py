#!/usr/bin/env python3
"""
招待制モニターベータの会社/ユーザーを管理するCLIツール。

管理API（/api/v1/admin/...）と同じ MonitorRepository を直接叩く。
最初の管理者アカウントは、管理API自体がまだ誰もログインできない
（=誰も叩けない）状態から始まるため、このCLIでの作成が唯一の経路になる。

PYTHONPATH を通して実行されることを前提とする（他の scripts/ 配下のスクリプトと同様）。
実行例:
  cd backend
  python ../scripts/manage_monitor_accounts.py create-company --name "Acme Inc" --slug acme --limit 100
  python ../scripts/manage_monitor_accounts.py create-user --company-slug acme --email user@acme.example --admin
  python ../scripts/manage_monitor_accounts.py list-usage
  python ../scripts/manage_monitor_accounts.py set-limit --company-slug acme --limit 200
  python ../scripts/manage_monitor_accounts.py deactivate-user --email user@acme.example
  python ../scripts/manage_monitor_accounts.py reset-password --email user@acme.example

価格・プラン定義（Starter/Growth/Pro/Monitor/Enterprise等）はコードではなくDB
（pricing_plansテーブル）で管理する。会社は個別上書き(--limit)を持てるほか、
プランに紐付けてそのプランのクレジット上限を継承できる（優先順位は
「個別上書き > プラン > 既定値」。詳細: docs/MONITOR_ACCOUNT_MANAGEMENT.md）。
  python ../scripts/manage_monitor_accounts.py create-plan --code growth --name "Growth" --price 79800 --credits 300
  python ../scripts/manage_monitor_accounts.py list-plans
  python ../scripts/manage_monitor_accounts.py update-plan --code growth --credits 350
  python ../scripts/manage_monitor_accounts.py assign-plan --company-slug acme --plan-code growth
  python ../scripts/manage_monitor_accounts.py clear-limit-override --company-slug acme
"""
import argparse
import secrets
import sys

try:
    from app.db.session import SessionLocal
    from app.db.base import Base
    from app.db.session import engine
    from app.repositories import MonitorRepository
except ImportError:
    print(
        "Error: 'app' module not found. Run with PYTHONPATH=backend, "
        "e.g.: cd backend && python ../scripts/manage_monitor_accounts.py ...",
        file=sys.stderr,
    )
    sys.exit(1)


def cmd_create_company(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        repo = MonitorRepository(db)
        if repo.get_company_by_slug(args.slug):
            print(f"Error: slug '{args.slug}' already exists.", file=sys.stderr)
            sys.exit(1)

        plan_id = None
        if args.plan_code:
            plan = repo.get_plan_by_code(args.plan_code)
            if not plan:
                print(f"Error: plan code '{args.plan_code}' not found. Create it first with create-plan.", file=sys.stderr)
                sys.exit(1)
            plan_id = plan.id

        company = repo.create_company(
            name=args.name, slug=args.slug, monthly_credit_limit=args.limit, plan_id=plan_id
        )
        effective_limit = repo.resolve_monthly_credit_limit(company)
        print(
            f"Created company: id={company.id} slug={company.slug} "
            f"monthly_credit_limit_override={company.monthly_credit_limit} "
            f"plan_id={company.plan_id} effective_monthly_credit_limit={effective_limit}"
        )
    finally:
        db.close()


def cmd_create_user(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        repo = MonitorRepository(db)
        company = repo.get_company_by_slug(args.company_slug)
        if not company:
            print(f"Error: company slug '{args.company_slug}' not found. Create it first.", file=sys.stderr)
            sys.exit(1)
        if repo.get_user_by_email(args.email):
            print(f"Error: email '{args.email}' already registered.", file=sys.stderr)
            sys.exit(1)

        password = args.password or secrets.token_urlsafe(9)
        user = repo.create_user(
            company_id=company.id,
            email=args.email,
            password=password,
            display_name=args.display_name,
            is_admin=args.admin,
        )
        print(f"Created user: id={user.id} email={user.email} company={company.slug} is_admin={user.is_admin}")
        if not args.password:
            print(f"Generated password (share via a separate secure channel): {password}")
    finally:
        db.close()


def cmd_set_limit(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        company = repo.get_company_by_slug(args.company_slug)
        if not company:
            print(f"Error: company slug '{args.company_slug}' not found.", file=sys.stderr)
            sys.exit(1)
        updated = repo.update_company(company.id, monthly_credit_limit=args.limit)
        print(f"Updated {updated.slug}: monthly_credit_limit_override={updated.monthly_credit_limit}")
    finally:
        db.close()


def cmd_clear_limit_override(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        company = repo.get_company_by_slug(args.company_slug)
        if not company:
            print(f"Error: company slug '{args.company_slug}' not found.", file=sys.stderr)
            sys.exit(1)
        updated = repo.update_company(company.id, clear_credit_limit_override=True)
        effective_limit = repo.resolve_monthly_credit_limit(updated)
        print(
            f"Cleared override for {updated.slug}. Now following plan/fallback: "
            f"effective_monthly_credit_limit={effective_limit}"
        )
    finally:
        db.close()


def cmd_assign_plan(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        company = repo.get_company_by_slug(args.company_slug)
        if not company:
            print(f"Error: company slug '{args.company_slug}' not found.", file=sys.stderr)
            sys.exit(1)
        plan = repo.get_plan_by_code(args.plan_code)
        if not plan:
            print(f"Error: plan code '{args.plan_code}' not found.", file=sys.stderr)
            sys.exit(1)
        updated = repo.update_company(
            company.id, plan_id=plan.id, clear_credit_limit_override=args.clear_override
        )
        effective_limit = repo.resolve_monthly_credit_limit(updated)
        print(
            f"Assigned plan '{plan.code}' to {updated.slug}. "
            f"override={updated.monthly_credit_limit} effective_monthly_credit_limit={effective_limit}"
        )
    finally:
        db.close()


def cmd_create_plan(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        Base.metadata.create_all(bind=engine)
        repo = MonitorRepository(db)
        if repo.get_plan_by_code(args.code):
            print(f"Error: plan code '{args.code}' already exists.", file=sys.stderr)
            sys.exit(1)
        plan = repo.create_plan(
            code=args.code,
            name=args.name,
            monthly_credit_limit=args.credits,
            monthly_price_jpy=args.price,
            marketing_note=args.note,
            is_public=not args.private,
            display_order=args.order,
        )
        print(
            f"Created plan: id={plan.id} code={plan.code} price={plan.monthly_price_jpy} "
            f"credits={plan.monthly_credit_limit} public={plan.is_public}"
        )
    finally:
        db.close()


def cmd_list_plans(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        plans = repo.list_plans()
        if not plans:
            print("No pricing plans registered yet.")
            return
        print(f"{'code':<14} {'name':<16} {'price(JPY)':<12} {'credits':<8} {'public':<7} {'active':<7} note")
        for plan in plans:
            price = "quote" if plan.monthly_price_jpy is None else str(plan.monthly_price_jpy)
            print(
                f"{plan.code:<14} {plan.name:<16} {price:<12} {plan.monthly_credit_limit:<8} "
                f"{str(plan.is_public):<7} {str(plan.is_active):<7} {plan.marketing_note or ''}"
            )
    finally:
        db.close()


def cmd_update_plan(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        plan = repo.get_plan_by_code(args.code)
        if not plan:
            print(f"Error: plan code '{args.code}' not found.", file=sys.stderr)
            sys.exit(1)
        is_public = None
        if args.public:
            is_public = True
        elif args.private:
            is_public = False
        is_active = None
        if args.active:
            is_active = True
        elif args.inactive:
            is_active = False
        updated = repo.update_plan(
            plan.id,
            monthly_credit_limit=args.credits,
            monthly_price_jpy=args.price,
            marketing_note=args.note,
            is_public=is_public,
            display_order=args.order,
            is_active=is_active,
        )
        print(
            f"Updated plan {updated.code}: price={updated.monthly_price_jpy} "
            f"credits={updated.monthly_credit_limit} public={updated.is_public} active={updated.is_active}"
        )
    finally:
        db.close()


def cmd_deactivate_company(args: argparse.Namespace) -> None:
    _set_company_active(args.company_slug, is_active=False)


def cmd_reactivate_company(args: argparse.Namespace) -> None:
    _set_company_active(args.company_slug, is_active=True)


def _set_company_active(slug: str, is_active: bool) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        company = repo.get_company_by_slug(slug)
        if not company:
            print(f"Error: company slug '{slug}' not found.", file=sys.stderr)
            sys.exit(1)
        updated = repo.update_company(company.id, is_active=is_active)
        print(f"{'Activated' if is_active else 'Deactivated'} company: {updated.slug}")
    finally:
        db.close()


def cmd_deactivate_user(args: argparse.Namespace) -> None:
    _set_user_active(args.email, is_active=False)


def cmd_reactivate_user(args: argparse.Namespace) -> None:
    _set_user_active(args.email, is_active=True)


def _set_user_active(email: str, is_active: bool) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        user = repo.get_user_by_email(email)
        if not user:
            print(f"Error: user '{email}' not found.", file=sys.stderr)
            sys.exit(1)
        repo.update_user(user.id, is_active=is_active)
        print(f"{'Activated' if is_active else 'Deactivated'} user: {email}")
    finally:
        db.close()


def cmd_reset_password(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        user = repo.get_user_by_email(args.email)
        if not user:
            print(f"Error: user '{args.email}' not found.", file=sys.stderr)
            sys.exit(1)
        new_password = args.password or secrets.token_urlsafe(9)
        repo.update_user(user.id, new_password=new_password)
        print(f"Password reset for {args.email}.")
        if not args.password:
            print(f"New password (share via a separate secure channel): {new_password}")
    finally:
        db.close()


def cmd_list_usage(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        repo = MonitorRepository(db)
        companies = repo.list_companies()
        if not companies:
            print("No monitor companies registered yet.")
            return
        print(f"{'slug':<20} {'name':<24} {'plan':<10} {'active':<8} {'used/limit(credits)':<20} {'remaining':<10}")
        for company in companies:
            usage = repo.get_usage_summary(company)
            plan = repo.get_plan_by_id(company.plan_id) if company.plan_id else None
            plan_label = plan.code if plan else "-"
            print(
                f"{company.slug:<20} {company.name:<24} {plan_label:<10} {str(company.is_active):<8} "
                f"{usage['used']}/{usage['limit']:<8} {usage['remaining']:<10}"
            )
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage CampaignPilot monitor beta accounts")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-company", help="Register a new monitor company")
    p.add_argument("--name", required=True)
    p.add_argument("--slug", required=True)
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Monthly credit limit override. If omitted, the company follows --plan-code's "
        "limit, or a fallback default (100) if neither is set.",
    )
    p.add_argument("--plan-code", required=False, help="Pricing plan to attach (see create-plan)")
    p.set_defaults(func=cmd_create_company)

    p = sub.add_parser("create-user", help="Invite a new monitor user into a company")
    p.add_argument("--company-slug", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=False, help="If omitted, a random password is generated")
    p.add_argument("--display-name", required=False)
    p.add_argument("--admin", action="store_true", help="Grant admin privileges to this user")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("set-limit", help="Set a company's monthly credit limit override")
    p.add_argument("--company-slug", required=True)
    p.add_argument("--limit", type=int, required=True)
    p.set_defaults(func=cmd_set_limit)

    p = sub.add_parser(
        "clear-limit-override",
        help="Remove a company's individual credit limit override (falls back to its plan, or the default)",
    )
    p.add_argument("--company-slug", required=True)
    p.set_defaults(func=cmd_clear_limit_override)

    p = sub.add_parser("assign-plan", help="Attach a pricing plan to a company")
    p.add_argument("--company-slug", required=True)
    p.add_argument("--plan-code", required=True)
    p.add_argument(
        "--clear-override",
        action="store_true",
        help="Also remove any individual credit limit override, so the plan's limit takes effect immediately",
    )
    p.set_defaults(func=cmd_assign_plan)

    p = sub.add_parser("deactivate-company", help="Suspend a monitor company (blocks all its users)")
    p.add_argument("--company-slug", required=True)
    p.set_defaults(func=cmd_deactivate_company)

    p = sub.add_parser("reactivate-company", help="Reactivate a suspended monitor company")
    p.add_argument("--company-slug", required=True)
    p.set_defaults(func=cmd_reactivate_company)

    p = sub.add_parser("deactivate-user", help="Suspend a single monitor user")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_deactivate_user)

    p = sub.add_parser("reactivate-user", help="Reactivate a suspended monitor user")
    p.add_argument("--email", required=True)
    p.set_defaults(func=cmd_reactivate_user)

    p = sub.add_parser("reset-password", help="Reset a monitor user's password")
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=False, help="If omitted, a random password is generated")
    p.set_defaults(func=cmd_reset_password)

    p = sub.add_parser("list-usage", help="Show all companies with this month's usage/limit")
    p.set_defaults(func=cmd_list_usage)

    p = sub.add_parser("create-plan", help="Register a new pricing plan (Starter/Growth/Pro/Monitor/...)")
    p.add_argument("--code", required=True, help="Unique code, e.g. 'starter', 'growth', 'pro', 'monitor'")
    p.add_argument("--name", required=True)
    p.add_argument("--credits", type=int, required=True, help="Monthly credit grant for this plan")
    p.add_argument("--price", type=int, required=False, help="Monthly price in JPY. Omit for quote-based plans")
    p.add_argument("--note", required=False, help="Marketing note, e.g. a campaign message")
    p.add_argument("--private", action="store_true", help="Mark as not publicly listed (e.g. Monitor plan)")
    p.add_argument("--order", type=int, default=0, help="Display order (ascending)")
    p.set_defaults(func=cmd_create_plan)

    p = sub.add_parser("list-plans", help="Show all pricing plans")
    p.set_defaults(func=cmd_list_plans)

    p = sub.add_parser("update-plan", help="Update an existing pricing plan")
    p.add_argument("--code", required=True)
    p.add_argument("--credits", type=int, required=False)
    p.add_argument("--price", type=int, required=False)
    p.add_argument("--note", required=False)
    p.add_argument("--order", type=int, required=False)
    p.add_argument("--public", action="store_true", help="Mark as publicly listed")
    p.add_argument("--private", action="store_true", help="Mark as not publicly listed")
    p.add_argument("--active", action="store_true", help="Reactivate this plan")
    p.add_argument("--inactive", action="store_true", help="Deactivate this plan (companies keep their assignment but it stops applying)")
    p.set_defaults(func=cmd_update_plan)

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
