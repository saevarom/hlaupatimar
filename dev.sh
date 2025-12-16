#!/bin/bash

# Development helper script for Hlaupatimar

case "$1" in
    "build")
        echo "Building Docker containers..."
        docker-compose build
        ;;
    "up")
        echo "Starting services..."
        docker-compose up -d
        ;;
    "down")
        echo "Stopping services..."
        docker-compose down
        ;;
    "logs")
        echo "Showing logs..."
        docker-compose logs -f web
        ;;
    "shell")
        echo "Opening Django shell..."
        docker-compose exec web python manage.py shell
        ;;
    "migrate")
        echo "Running migrations..."
        docker-compose exec web python manage.py migrate
        ;;
    "superuser")
        echo "Creating superuser..."
        docker-compose exec web python manage.py createsuperuser
        ;;
    "test")
        echo "Running tests..."
        docker-compose exec web python manage.py test
        ;;
    "reset-db")
        echo "Resetting database..."
        docker-compose down -v
        docker-compose up -d db
        sleep 5
        docker-compose up -d web
        ;;
    *)
        echo "Usage: $0 {build|up|down|logs|shell|migrate|superuser|test|reset-db}"
        echo ""
        echo "Commands:"
        echo "  build     - Build Docker containers"
        echo "  up        - Start all services"
        echo "  down      - Stop all services"
        echo "  logs      - Show web service logs"
        echo "  shell     - Open Django shell"
        echo "  migrate   - Run database migrations"
        echo "  superuser - Create Django superuser"
        echo "  test      - Run tests"
        echo "  reset-db  - Reset database (WARNING: destroys all data)"
        ;;
esac
