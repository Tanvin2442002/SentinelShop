.RECIPEPREFIX = >
.DEFAULT_GOAL := up
COMPOSE := docker compose

.PHONY: env up down clean logs ps smoke

env:
> test -f .env || (cp .env.example .env \
>   && sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$$(openssl rand -hex 16)/; s/^SECRET_KEY=.*/SECRET_KEY=$$(openssl rand -hex 32)/" .env \
>   && echo "created .env with generated secrets")

up: env
> $(COMPOSE) up -d --build --wait --wait-timeout 180
> @echo "stack is up on the port set by EDGE_PORT in .env (default 8080)"

down:
> $(COMPOSE) down

clean:
> $(COMPOSE) down -v

logs:
> $(COMPOSE) logs -f --tail 50

ps:
> $(COMPOSE) ps

smoke:
> bash scripts/smoke-test.sh
