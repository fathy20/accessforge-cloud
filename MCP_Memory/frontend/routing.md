# Routing
Uses **TanStack Router** (outeTree.gen.ts).
- /_authenticated: Layout route requiring valid Supabase session.
- /_authenticated/admin: Layout route requiring super_admin or dmin role.
- Data Loaders fetch user permissions before rendering a route.
