from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioResponse,
    PortfolioUpdate,
)

# Used to get the database session
from app.database.connection import get_db

# Used to identify the authenticated user from the JWT
from app.auth.security import get_current_user

# This is the Database model
from app.models.portfolio import Portfolio

# Pydantic schemas
from app.schemas.portfolio import PortfolioCreate, PortfolioResponse


# Create the router for portfolio-related endpoints
router = APIRouter(
    prefix="/portfolios",
    tags=["Portfolios"],
)


@router.post(
    "/",
    response_model=PortfolioResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_portfolio(
    portfolio_data: PortfolioCreate,
    # Get a database session for this request
    db: Session = Depends(get_db),

    # Get the currently authenticated user from the JWT
    current_user=Depends(get_current_user),
):
    # Create a new portfolio.
    #
    # Notice that we DON'T get user_id from the request.
    # We get it from the authenticated user's JWT instead.
    new_portfolio = Portfolio(
        user_id=current_user.id,
        name=portfolio_data.name,
    )

    # Add the new portfolio to the database session
    db.add(new_portfolio)

    # Save the new portfolio to PostgreSQL
    db.commit()

    # Refresh the object so SQLAlchemy gets the generated
    # id and created_at values from PostgreSQL
    db.refresh(new_portfolio)

    # Return the newly created portfolio
    return new_portfolio

@router.get(
    "/",
    response_model=list[PortfolioResponse],
)
def get_portfolios(
    # Get a database session for this request.
    db: Session = Depends(get_db),

    # Identify the user from the JWT.
    current_user=Depends(get_current_user),
):
    # Get only portfolios belonging to the authenticated user.
    portfolios = (
        db.query(Portfolio)
        .filter(Portfolio.user_id == current_user.id)
        .all()
    )

    # Return the user's portfolios.
    return portfolios

@router.get(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
)

def get_portfolio(
    portfolio_id: int,

    # Get a database session for this request.
    db: Session = Depends(get_db),

    # Identify the authenticated user from the JWT.
    current_user=Depends(get_current_user),
):
    # Find the requested portfolio, but ONLY if it belongs
    # to the currently authenticated user.
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
        .first()
    )

    # If the portfolio doesn't exist OR belongs to another
    # user, return a 404 response.
    if portfolio is None:

        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )

    # Return the portfolio.
    return portfolio

@router.put(
    "/{portfolio_id}",
    response_model=PortfolioResponse,
)

def update_portfolio(
    portfolio_id: int,

    # The new portfolio information sent by the user.
    portfolio_data: PortfolioUpdate,

    # Get a database session for this request.
    db: Session = Depends(get_db),

    # Identify the authenticated user from the JWT.
    current_user=Depends(get_current_user),
):
    # Find the portfolio, but ONLY if it belongs to
    # the currently authenticated user.
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
        .first()
    )

    # If the portfolio doesn't exist or belongs to
    # another user, don't allow the update.
    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )

    # Update the portfolio name.
    portfolio.name = portfolio_data.name

    # Save the change to PostgreSQL.
    db.commit()

    # Refresh the object so the response contains
    # the latest database values.
    db.refresh(portfolio)

    # Return the updated portfolio.
    return portfolio

@router.delete(
    "/{portfolio_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)

def delete_portfolio(
    portfolio_id: int,

    # Get a database session for this request.
    db: Session = Depends(get_db),

    # Identify the authenticated user from the JWT.
    current_user=Depends(get_current_user),
):
    # Find the portfolio, but ONLY if it belongs to
    # the currently authenticated user.
    portfolio = (
        db.query(Portfolio)
        .filter(
            Portfolio.id == portfolio_id,
            Portfolio.user_id == current_user.id,
        )
        .first()
    )

    # If the portfolio doesn't exist or belongs to
    # another user, don't allow the deletion.
    if portfolio is None:
        raise HTTPException(
            status_code=404,
            detail="Portfolio not found",
        )

    # Delete the portfolio from the database session.
    db.delete(portfolio)

    # Permanently save the deletion to PostgreSQL.
    db.commit()