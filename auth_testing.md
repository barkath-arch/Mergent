# Auth Testing Playbook — MERGENT V1

## MongoDB Verification
```
mongosh
use test_database
db.users.find({role: "admin"}).pretty()
db.users.findOne({role: "admin"}, {password_hash: 1})
```
- bcrypt hash starts with `$2b$`
- indexes: users.email unique; login_attempts.identifier; password_reset_tokens.expires_at TTL

## API Testing
```
API=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d'=' -f2)
curl -c c.txt -X POST $API/api/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"rohit@mergent.demo","password":"Demo!Pass123"}'
curl -b c.txt $API/api/auth/me
```

Demo accounts (from /app/memory/test_credentials.md):
- buyer:   rohit@mergent.demo  / Demo!Pass123
- builder: aman@mergent.demo   / Demo!Pass123
- admin:   admin@mergent.demo  / AdminPass123
