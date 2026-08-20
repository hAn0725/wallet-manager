"""分类管理 —— 增删改查,删除存在账单的分类时安全处理。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.database.database import get_connection
from app.utils.helpers import round2


@dataclass
class Category:
    id: Optional[int]
    name: str
    icon: str
    type: str
    is_default: bool
    sort_order: int


def list_categories(type_filter: Optional[str] = None) -> list[Category]:
    sql = "SELECT * FROM categories"
    params: list = []
    if type_filter:
        sql += " WHERE type=?"
        params.append(type_filter)
    sql += " ORDER BY sort_order, id"
    rows = get_connection().execute(sql, params).fetchall()
    return [_row(r) for r in rows]


def _row(r) -> Category:
    return Category(
        id=r["id"], name=r["name"], icon=r["icon"], type=r["type"],
        is_default=bool(r["is_default"]), sort_order=r["sort_order"],
    )


def get_category(cid: int) -> Optional[Category]:
    row = get_connection().execute(
        "SELECT * FROM categories WHERE id=?", (cid,)
    ).fetchone()
    return _row(row) if row else None


def add_category(name: str, icon: str, type_: str) -> int:
    name = (name or "").strip()
    icon = (icon or "").strip()
    if not name:
        raise ValueError("分类名称不能为空")
    if type_ not in ("income", "expense"):
        raise ValueError("类型必须是 income 或 expense")
    conn = get_connection()
    # 最大 sort_order
    row = conn.execute(
        "SELECT COALESCE(MAX(sort_order),-1)+1 AS s FROM categories WHERE type=?",
        (type_,),
    ).fetchone()
    cid = conn.execute(
        "INSERT INTO categories(name,icon,type,is_default,sort_order) "
        "VALUES(?,?,?,0,?)",
        (name, icon, type_, row["s"]),
    ).lastrowid
    conn.commit()
    return cid


def update_category(cid: int, name: str, icon: str) -> None:
    name = (name or "").strip()
    if not name:
        raise ValueError("分类名称不能为空")
    cat = get_category(cid)
    if cat is None:
        raise ValueError("分类不存在")
    if cat.is_default and name != cat.name:
        # 允许修改默认分类名称,但提示
        pass
    conn = get_connection()
    conn.execute("UPDATE categories SET name=?, icon=? WHERE id=?", (name, icon, cid))
    conn.commit()


def category_transaction_count(cid: int) -> int:
    row = get_connection().execute(
        "SELECT COUNT(*) AS c FROM transactions WHERE category_id=?", (cid,)
    ).fetchone()
    return row["c"]


def delete_category(cid: int) -> None:
    """删除分类。存在账单时 ON DELETE SET NULL,账单保留但变未分类。
    为安全,默认分类也允许删除(用户可能想精简)。"""
    cat = get_category(cid)
    if cat is None:
        raise ValueError("分类不存在")
    conn = get_connection()
    conn.execute("DELETE FROM categories WHERE id=?", (cid,))
    conn.commit()
