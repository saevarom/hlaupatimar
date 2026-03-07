# Hlaupatimar - Icelandic Running Competitions API

A Django-based API for aggregating and managing data about running competitions and races in Iceland. Built with Django Ninja for modern API development and PostgreSQL for robust data storage.

## Features

- **Race Management**: Create, read, update, and delete race information
- **Results Tracking**: Store and retrieve race results with detailed participant information
- **Split Times**: Track intermediate split times for races
- **Filtering & Search**: Advanced filtering and search capabilities
- **RESTful API**: Clean, documented API endpoints using Django Ninja
- **Admin Interface**: Django admin interface for easy data management

## Tech Stack

- **Backend**: Django 4.2 with Django Ninja
- **Database**: PostgreSQL 15
- **Containerization**: Docker & Docker Compose
- **API Documentation**: Automatic OpenAPI/Swagger documentation

## Quick Start

### Prerequisites

- Docker and Docker Compose installed on your system

### Installation

1. Clone the repository:
```bash
git clone <your-repo-url>
cd hlaupatimar
```

2. Copy the environment file:
```bash
cp .env.example .env
```

3. Build and start the services:
```bash
docker-compose up --build
```

4. Run migrations (in a new terminal):
```bash
docker-compose exec web python manage.py migrate
```

5. Create a superuser (optional):
```bash
docker-compose exec web python manage.py createsuperuser
```

The API will be available at http://localhost:8002/api/
The admin interface will be available at http://localhost:8002/admin/

## Deploy on Render (Git-based)

This repository includes a Render Blueprint file at `render.yaml` for:
- Django API service (`hlaupatimar-api`)
- Static React frontend (`hlaupatimar-frontend`)
- Managed PostgreSQL database (`hlaupatimar-db`)

### Steps

1. Push this repository to GitHub.
2. In Render, create a new **Blueprint** and select this repo.
3. Render will provision services from `render.yaml`.
4. Use `main` as your deploy branch.

After setup, every push to the connected branch triggers a deploy.

## Deploy on Ubuntu Server (Docker Compose)

This repository also includes a server-oriented stack:
- `docker-compose.server.yml`
- `frontend/Dockerfile.prod`
- `frontend/nginx.prod.conf`
- `.env.server.example`

Quick deploy steps:

```bash
cp .env.server.example .env.server
# edit .env.server secrets and hosts
sudo docker compose -f docker-compose.server.yml up -d --build
```

### One-command deploy script

Use the included script from your local machine:

```bash
./deploy-server.sh
```

Optional push before deploy:

```bash
./deploy-server.sh --push
```

## API Endpoints

### Races
- `GET /api/races/` - List all races (with filtering)
- `POST /api/races/` - Create a new race
- `GET /api/races/{id}` - Get a specific race
- `PUT /api/races/{id}` - Update a race
- `DELETE /api/races/{id}` - Delete a race
- `GET /api/races/search?q=query` - Search races

### Results
- `GET /api/races/{race_id}/results` - List results for a race
- `POST /api/races/{race_id}/results` - Create a new result
- `GET /api/races/results/{result_id}` - Get a specific result

### Splits
- `GET /api/races/results/{result_id}/splits` - List splits for a result
- `POST /api/races/results/{result_id}/splits` - Create a new split

## API Documentation

Once the server is running, you can access the interactive API documentation at:
- Swagger UI: http://localhost:8002/api/docs
- ReDoc: http://localhost:8002/api/redoc

## Data Models

### Race
- Basic race information (name, date, location, type)
- Distance and elevation details
- Registration and organizational info
- Entry fees and participant limits

### Result
- Participant information (name, age, gender, nationality, club)
- Race performance (finish time, gun time, placement)
- Status tracking (finished, DNF, DNS, DQ)

### Split
- Intermediate timing data
- Distance markers and split times
- Cumulative timing information

## Development

### Running Commands

```bash
# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Run tests
docker-compose exec web python manage.py test

# Access Django shell
docker-compose exec web python manage.py shell

# View logs
docker-compose logs -f web

# Enhanced Django shell
docker-compose exec web python manage.py shell_plus
```

### Frontend (Runner Trends UI)

A React frontend is available in `frontend/` for:
- searching runners
- opening a runner profile page
- visualizing trends over time for 5K, 10K, half marathon, marathon, and other categories

```bash
# Start backend API
docker-compose up web

# Start frontend (in a separate terminal)
docker-compose up frontend
```

The frontend uses `/api` and proxies to `http://localhost:8002` in development.
Start the Django API first (`docker-compose up`) before opening the frontend.

### Database Access

```bash
# Access PostgreSQL directly
docker-compose exec db psql -U hlaupatimar_user -d hlaupatimar
```

## Environment Variables

Key environment variables (see `.env.example`):

- `DEBUG`: Enable debug mode (development only)
- `SECRET_KEY`: Django secret key (generate a secure one for production)
- `DATABASE_URL`: PostgreSQL connection string

## Future Features

- Data scraping modules for Icelandic race websites
- Advanced analytics and statistics
- User authentication and race registration
- Export functionality (CSV, Excel)
- Real-time race tracking
- Mobile API optimizations

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
