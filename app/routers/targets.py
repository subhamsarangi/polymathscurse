from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.core.permissions import (
    require_interest_owned,
    require_interest_interactive,
    require_target_owned,
)
from app.db.session import get_db
from app.models.user import User
from app.models.target import Target, TargetBullet, Todo
from app.models.interest import Interest
from app.schemas.target import (
    TargetCreate,
    TargetOut,
    TargetRename,
    BulletIn,
    BulletOut,
    TodoCreate,
    TodoEdit,
    TodoOut,
)


from app.schemas.tree import TargetDetailOut, BulletOut, GroupedTodosOut, TodoOut

router = APIRouter(prefix="/targets", tags=["targets"])

TODO_ACTIVE_LIMIT = 2
TODO_BACKLOG_LIMIT = 3
BULLETS_LIMIT = 3


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_interest_interactive_by_target(
    db: Session, user_id: str, target_id: str
) -> Interest:
    interest = (
        db.query(Interest)
        .join(Target, Target.interest_id == Interest.id)
        .filter(Target.id == target_id, Interest.user_id == user_id)
        .first()
    )
    if not interest:
        raise HTTPException(status_code=404, detail="Target not found")
    require_interest_interactive(interest)
    return interest


@router.get("/by-interest/{interest_id}", response_model=list[TargetOut])
def list_targets_for_interest(
    interest_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = require_interest_owned(db, str(user.id), interest_id)

    targets = (
        db.query(Target)
        .filter(Target.interest_id == interest.id)
        .order_by(Target.sort_order.asc(), Target.updated_at.desc())
        .all()
    )
    return [
        TargetOut(
            id=str(t.id),
            interest_id=str(t.interest_id),
            name=t.name,
            sort_order=t.sort_order,
        )
        for t in targets
    ]


@router.post("/by-interest/{interest_id}", response_model=TargetOut, status_code=201)
def create_target(
    interest_id: str,
    payload: TargetCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    interest = require_interest_owned(db, str(user.id), interest_id)
    require_interest_interactive(interest)

    t = Target(interest_id=interest.id, name=payload.name.strip())
    db.add(t)
    db.commit()
    db.refresh(t)
    return TargetOut(
        id=str(t.id),
        interest_id=str(t.interest_id),
        name=t.name,
        sort_order=t.sort_order,
    )


@router.patch("/{target_id}", response_model=TargetOut)
def rename_target(
    target_id: str,
    payload: TargetRename,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    _ensure_interest_interactive_by_target(db, str(user.id), target_id)

    target.name = payload.name.strip()
    db.add(target)
    db.commit()
    db.refresh(target)
    return TargetOut(
        id=str(target.id),
        interest_id=str(target.interest_id),
        name=target.name,
        sort_order=target.sort_order,
    )


@router.delete("/{target_id}", status_code=204)
def delete_target(
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    _ensure_interest_interactive_by_target(db, str(user.id), target_id)

    db.delete(target)
    db.commit()
    return None


# -------- Bullets (max 3 per target) --------


@router.get("/{target_id}/bullets", response_model=list[BulletOut])
def list_bullets(
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    bullets = (
        db.query(TargetBullet)
        .filter(TargetBullet.target_id == target.id)
        .order_by(TargetBullet.sort_order.asc(), TargetBullet.updated_at.desc())
        .all()
    )
    return [
        BulletOut(
            id=str(b.id),
            target_id=str(b.target_id),
            content=b.content,
            category=b.category,
            sort_order=b.sort_order,
        )
        for b in bullets
    ]


@router.put("/{target_id}/bullets", response_model=list[BulletOut])
def replace_bullets(
    target_id: str,
    payload: list[BulletIn],
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    _ensure_interest_interactive_by_target(db, str(user.id), target_id)

    if len(payload) > BULLETS_LIMIT:
        raise HTTPException(
            status_code=409, detail=f"Max {BULLETS_LIMIT} bullets allowed"
        )

    # delete existing, insert new
    db.query(TargetBullet).filter(TargetBullet.target_id == target.id).delete()
    db.flush()

    new_rows: list[TargetBullet] = []
    for i, item in enumerate(payload):
        content = item.content.strip()
        if not content:
            raise HTTPException(
                status_code=400, detail="Bullet content cannot be empty"
            )
        new_rows.append(
            TargetBullet(
                target_id=target.id,
                content=content,
                category=item.category,
                sort_order=item.sort_order if item.sort_order is not None else i,
            )
        )

    db.add_all(new_rows)
    db.commit()

    bullets = (
        db.query(TargetBullet)
        .filter(TargetBullet.target_id == target.id)
        .order_by(TargetBullet.sort_order.asc(), TargetBullet.updated_at.desc())
        .all()
    )

    return [
        BulletOut(
            id=str(b.id),
            target_id=str(b.target_id),
            content=b.content,
            category=b.category,
            sort_order=b.sort_order,
        )
        for b in bullets
    ]


# -------- Todos (active<=2, backlog<=3, done unlimited) --------


@router.get("/{target_id}/todos", response_model=list[TodoOut])
def list_todos(
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    todos = (
        db.query(Todo)
        .filter(Todo.target_id == target.id)
        .order_by(
            # active first, then backlog, then done
            func.case(
                (Todo.status == "ACTIVE", 0),
                (Todo.status == "BACKLOG", 1),
                else_=2,
            ),
            Todo.created_at.desc(),
        )
        .all()
    )
    return [
        TodoOut(
            id=str(t.id),
            target_id=str(t.target_id),
            status=t.status,
            content=t.content,
            created_at=t.created_at,
            done_at=t.done_at,
        )
        for t in todos
    ]


def _count_by_status(db: Session, target_id: str, status_name: str) -> int:
    return int(
        db.query(func.count(Todo.id))
        .filter(and_(Todo.target_id == target_id, Todo.status == status_name))
        .scalar()
        or 0
    )


@router.post("/{target_id}/todos", response_model=TodoOut, status_code=201)
def create_todo(
    target_id: str,
    payload: TodoCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = require_target_owned(db, str(user.id), target_id)
    _ensure_interest_interactive_by_target(db, str(user.id), target_id)

    status_name = payload.status.upper().strip()
    if status_name not in {"ACTIVE", "BACKLOG"}:
        raise HTTPException(status_code=400, detail="status must be ACTIVE or BACKLOG")

    if status_name == "ACTIVE":
        if _count_by_status(db, str(target.id), "ACTIVE") >= TODO_ACTIVE_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Active todo limit reached (max {TODO_ACTIVE_LIMIT})",
            )
    else:
        if _count_by_status(db, str(target.id), "BACKLOG") >= TODO_BACKLOG_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Backlog todo limit reached (max {TODO_BACKLOG_LIMIT})",
            )

    todo = Todo(
        target_id=target.id, status=status_name, content=payload.content.strip()
    )
    db.add(todo)
    db.commit()
    db.refresh(todo)

    return TodoOut(
        id=str(todo.id),
        target_id=str(todo.target_id),
        status=todo.status,
        content=todo.content,
        created_at=todo.created_at,
        done_at=todo.done_at,
    )


@router.patch("/todos/{todo_id}", response_model=TodoOut)
def edit_todo(
    todo_id: str,
    payload: TodoEdit,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ensure ownership + interactivity via join
    todo = (
        db.query(Todo)
        .join(Target, Target.id == Todo.target_id)
        .join(Interest, Interest.id == Target.interest_id)
        .filter(Todo.id == todo_id, Interest.user_id == user.id)
        .first()
    )
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    require_interest_interactive(
        todo.target.target.interest
        if False
        else _ensure_interest_interactive_by_target(
            db, str(user.id), str(todo.target_id)
        )
    )

    todo.content = payload.content.strip()
    db.add(todo)
    db.commit()
    db.refresh(todo)

    return TodoOut(
        id=str(todo.id),
        target_id=str(todo.target_id),
        status=todo.status,
        content=todo.content,
        created_at=todo.created_at,
        done_at=todo.done_at,
    )


@router.post("/todos/{todo_id}/mark-done", response_model=TodoOut)
def mark_done(
    todo_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    todo = (
        db.query(Todo)
        .join(Target, Target.id == Todo.target_id)
        .join(Interest, Interest.id == Target.interest_id)
        .filter(Todo.id == todo_id, Interest.user_id == user.id)
        .first()
    )
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    _ensure_interest_interactive_by_target(db, str(user.id), str(todo.target_id))

    todo.status = "DONE"
    todo.done_at = _utcnow()
    db.add(todo)
    db.commit()
    db.refresh(todo)

    return TodoOut(
        id=str(todo.id),
        target_id=str(todo.target_id),
        status=todo.status,
        content=todo.content,
        created_at=todo.created_at,
        done_at=todo.done_at,
    )


@router.post("/todos/{todo_id}/move", response_model=TodoOut)
def move_todo(
    todo_id: str,
    new_status: str,  # query param: ACTIVE or BACKLOG
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    new_status = new_status.upper().strip()
    if new_status not in {"ACTIVE", "BACKLOG"}:
        raise HTTPException(
            status_code=400, detail="new_status must be ACTIVE or BACKLOG"
        )

    todo = (
        db.query(Todo)
        .join(Target, Target.id == Todo.target_id)
        .join(Interest, Interest.id == Target.interest_id)
        .filter(Todo.id == todo_id, Interest.user_id == user.id)
        .first()
    )
    if not todo:
        raise HTTPException(status_code=404, detail="Todo not found")

    _ensure_interest_interactive_by_target(db, str(user.id), str(todo.target_id))

    if todo.status == "DONE":
        raise HTTPException(
            status_code=409, detail="Cannot move a DONE todo back to active/backlog"
        )

    if new_status == todo.status:
        db.refresh(todo)
        return TodoOut(
            id=str(todo.id),
            target_id=str(todo.target_id),
            status=todo.status,
            content=todo.content,
            created_at=todo.created_at,
            done_at=todo.done_at,
        )

    if new_status == "ACTIVE":
        if _count_by_status(db, str(todo.target_id), "ACTIVE") >= TODO_ACTIVE_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Active todo limit reached (max {TODO_ACTIVE_LIMIT})",
            )
    else:
        if _count_by_status(db, str(todo.target_id), "BACKLOG") >= TODO_BACKLOG_LIMIT:
            raise HTTPException(
                status_code=409,
                detail=f"Backlog todo limit reached (max {TODO_BACKLOG_LIMIT})",
            )

    todo.status = new_status
    db.add(todo)
    db.commit()
    db.refresh(todo)

    return TodoOut(
        id=str(todo.id),
        target_id=str(todo.target_id),
        status=todo.status,
        content=todo.content,
        created_at=todo.created_at,
        done_at=todo.done_at,
    )


@router.get("/{target_id}/detail", response_model=TargetDetailOut)
def get_target_detail(
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = (
        db.query(Target)
        .join(Interest, Interest.id == Target.interest_id)
        .filter(Target.id == target_id, Interest.user_id == user.id)
        .first()
    )
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    bullets = (
        db.query(TargetBullet)
        .filter(TargetBullet.target_id == target.id)
        .order_by(TargetBullet.sort_order.asc(), TargetBullet.updated_at.desc())
        .all()
    )
    bullets_out = [
        BulletOut(
            id=str(b.id),
            content=b.content,
            category=b.category,
            sort_order=b.sort_order,
        )
        for b in bullets
    ]

    todos = (
        db.query(Todo)
        .filter(Todo.target_id == target.id)
        .order_by(Todo.created_at.desc())
        .all()
    )

    active: list[TodoOut] = []
    backlog: list[TodoOut] = []
    done: list[TodoOut] = []

    for t in todos:
        item = TodoOut(
            id=str(t.id),
            status=t.status,
            content=t.content,
            created_at=t.created_at,
            done_at=t.done_at,
        )
        if t.status == "ACTIVE":
            active.append(item)
        elif t.status == "BACKLOG":
            backlog.append(item)
        else:
            done.append(item)

    return TargetDetailOut(
        id=str(target.id),
        interest_id=str(target.interest_id),
        name=target.name,
        bullets=bullets_out,
        todos=GroupedTodosOut(active=active, backlog=backlog, done=done),
    )
