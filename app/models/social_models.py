from sqlalchemy import (
    BigInteger, Boolean, Column, Float, Integer, String, Text, UniqueConstraint, ForeignKey, inspect, text
)
from sqlalchemy.orm import relationship

from app.database import Base


class SocialPost(Base):
    __tablename__ = "social_posts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    user_name = Column(String(255))
    content = Column(Text)
    image_url = Column(Text)
    media_type = Column(String(20))  # "image" or "video"
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    is_global = Column(Boolean, default=False, nullable=False)
    created_at = Column(BigInteger, nullable=False)  # unix milliseconds

    comments = relationship("SocialComment", back_populates="post", cascade="all, delete-orphan")
    likes = relationship("SocialLike", back_populates="post", cascade="all, delete-orphan")


class SocialComment(Base):
    __tablename__ = "social_comments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(String(255), nullable=False)
    user_name = Column(String(255))
    content = Column(Text)
    created_at = Column(BigInteger, nullable=False)

    post = relationship("SocialPost", back_populates="comments")


class SocialLike(Base):
    __tablename__ = "social_likes"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    post_id = Column(BigInteger, ForeignKey("social_posts.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(255), nullable=False)
    created_at = Column(BigInteger, nullable=False)

    __table_args__ = (UniqueConstraint("post_id", "user_id", name="uq_like_post_user"),)

    post = relationship("SocialPost", back_populates="likes")


class SocialConversation(Base):
    __tablename__ = "social_conversations"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    owner_id = Column(String(255), nullable=False, index=True)
    other_user_id = Column(String(255), nullable=False)
    other_user_name = Column(String(255))
    last_message = Column(Text)
    updated_at = Column(BigInteger, nullable=False)
    unread_count = Column(Integer, default=0)
    hidden_by = Column(Text, default="")  # comma-separated emails of users who hid this conversation

    __table_args__ = (UniqueConstraint("owner_id", "other_user_id", name="uq_conv_owner_other"),)

    messages = relationship("SocialMessage", back_populates="conversation", cascade="all, delete-orphan")


class SocialMessage(Base):
    __tablename__ = "social_messages"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id = Column(BigInteger, ForeignKey("social_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_id = Column(String(255), nullable=False)
    sender_name = Column(String(255))
    content = Column(Text)
    created_at = Column(BigInteger, nullable=False)
    is_delivered = Column(Boolean, default=False, nullable=False)
    delivered_at = Column(BigInteger, nullable=True)
    is_read = Column(Boolean, default=False)
    seen_at = Column(BigInteger, nullable=True)
    deleted_by = Column(Text, default="")  # comma-separated emails of users who deleted this message

    conversation = relationship("SocialConversation", back_populates="messages")


class SocialProfile(Base):
    __tablename__ = "social_profiles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, unique=True, index=True)
    display_name = Column(String(255))
    avatar_url = Column(Text)
    bio = Column(Text)
    location = Column(String(255))
    crops = Column(Text)
    farm_type = Column(String(255))
    soil_type = Column(String(255))
    irrigation_type = Column(String(255))
    experience_level = Column(String(255))
    planting_months = Column(Text)
    goals = Column(Text)


def ensure_social_schema(engine) -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "social_posts" not in tables:
        return

    statements = []

    existing_posts = {column["name"] for column in inspector.get_columns("social_posts")}
    if "latitude" not in existing_posts:
        statements.append("ALTER TABLE social_posts ADD COLUMN latitude FLOAT")
    if "longitude" not in existing_posts:
        statements.append("ALTER TABLE social_posts ADD COLUMN longitude FLOAT")
    if "is_global" not in existing_posts:
        statements.append("ALTER TABLE social_posts ADD COLUMN is_global BOOLEAN DEFAULT FALSE")

    if "social_messages" in tables:
        existing_msgs = {column["name"] for column in inspector.get_columns("social_messages")}
        if "deleted_by" not in existing_msgs:
            statements.append("ALTER TABLE social_messages ADD COLUMN deleted_by TEXT DEFAULT ''")
        if "is_delivered" not in existing_msgs:
            statements.append("ALTER TABLE social_messages ADD COLUMN is_delivered BOOLEAN DEFAULT FALSE")
        if "delivered_at" not in existing_msgs:
            statements.append("ALTER TABLE social_messages ADD COLUMN delivered_at BIGINT")
        if "seen_at" not in existing_msgs:
            statements.append("ALTER TABLE social_messages ADD COLUMN seen_at BIGINT")

    if "social_conversations" in tables:
        existing_convs = {column["name"] for column in inspector.get_columns("social_conversations")}
        if "hidden_by" not in existing_convs:
            statements.append("ALTER TABLE social_conversations ADD COLUMN hidden_by TEXT DEFAULT ''")

    if "social_profiles" in tables:
        existing_profiles = {column["name"] for column in inspector.get_columns("social_profiles")}
        if "avatar_url" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN avatar_url TEXT")
        if "crops" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN crops TEXT")
        if "farm_type" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN farm_type VARCHAR(255)")
        if "soil_type" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN soil_type VARCHAR(255)")
        if "irrigation_type" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN irrigation_type VARCHAR(255)")
        if "experience_level" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN experience_level VARCHAR(255)")
        if "planting_months" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN planting_months TEXT")
        if "goals" not in existing_profiles:
            statements.append("ALTER TABLE social_profiles ADD COLUMN goals TEXT")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
