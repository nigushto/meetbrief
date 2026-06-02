import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=100,
    messages=[
        {"role": "user", "content": "Say hello in exactly 10 words."}
    ]
)

print("API connected successfully!")
print("Response:", message.content[0].text)
print("Model:", message.model)
print("Input tokens used:", message.usage.input_tokens)
print("Output tokens used:", message.usage.output_tokens)