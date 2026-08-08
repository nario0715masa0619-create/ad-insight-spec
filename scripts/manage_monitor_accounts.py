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
        company = repo.create_company(name=args.name, slug=args.slug, monthly_credit_limit=args.limit)
        print(f"Created company: id={company.id} slug={company.slug} monthly_credit_limit={company.monthly_credit_limit}")
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
        print(f"Updated {updated.slug}: monthly_credit_limit={updated.monthly_credit_limit}")
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
        print(f"{'slug':<20} {'name':<24} {'active':<8} {'used/limit(credits)':<20} {'remaining':<10}")
        for company in companies:
            usage = repo.get_usage_summary(company)
            print(
                f"{company.slug:<20} {company.name:<24} {str(company.is_active):<8} "
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
    p.add_argument("--limit", type=int, default=100, help="Monthly credit limit (default: 100)")
    p.set_defaults(func=cmd_create_company)

    p = sub.add_parser("create-user", help="Invite a new monitor user into a company")
    p.add_argument("--company-slug", required=True)
    p.add_argument("--email", required=True)
    p.add_argument("--password", required=False, help="If omitted, a random password is generated")
    p.add_argument("--display-name", required=False)
    p.add_argument("--admin", action="store_true", help="Grant admin privileges to this user")
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("set-limit", help="Change a company's monthly credit limit")
    p.add_argument("--company-slug", required=True)
    p.add_argument("--limit", type=int, required=True)
    p.set_defaults(func=cmd_set_limit)

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

    return parser


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.func(args)
