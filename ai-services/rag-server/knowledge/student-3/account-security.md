# KICKLAB Customer Account Security

A customer changing their password must provide their current password.

The new password must contain at least 8 characters.

Before changing the password, the Customer Account backend verifies the current
password against the stored password hash.

Passwords are stored as hashes rather than plain-text passwords.

Normal customer API responses do not expose the stored password hash.

Authentication-specific database operations may access the password hash
internally so that the backend can verify a submitted password.

A customer whose account status is not Active cannot log in.