# Database setup

Run migrations `001` through `005`, then product and inventory seeds. After creating
Create the demo Auth users, run `seed/003_demo_workspace.sql`, then run
`seed/004_multi_user_demo.sql`. The latter assigns three retail members and three
ADMIN/operator accounts to the shared demo group. See `docs/MULTI_USER_MVP_TEST.md`.
It resolves the Auth UUID automatically and creates the demo group and open order cycle.
