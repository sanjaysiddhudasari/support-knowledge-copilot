from app.auth.client import supabase


# response = supabase.auth.sign_up(
#     {
#         "email": "sanjaysiddhu999@gmail.com",
#         "password": "TestPassword123!",
#     }
# )

# print(response)


response = supabase.auth.sign_in_with_password({
    "email": "sanjaysiddhu999@gmail.com",
    "password": "TestPassword123!",
})

print(response.session.access_token)