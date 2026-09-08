# Database setup

Run migrations `001` through `005`, then product and inventory seeds. After creating
`demo.member@sharemybread.test` in Supabase Auth, run `seed/003_demo_workspace.sql`.
It resolves the Auth UUID automatically and creates the demo group and open order cycle.
