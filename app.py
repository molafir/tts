def generate_audio(client, model, input_blocks, speech_config, stream, mime_type, sample_rate):
    started = time.time()
    
    # تنظیمات ایمنی برای غیرفعال کردن فیلتر
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    ]

    if stream:
        # ... (کد استریم)
        response = client.interactions.create(
            model=model, input=input_blocks,
            response_format={"type": "audio"},
            generation_config={"speech_config": speech_config},
            safety_settings=safety_settings, # <-- اضافه شد
            stream=True,
        )
        # ...
    
    # ...
    response = create_with_retry(
        client,
        model=model, input=input_blocks,
        response_format=response_format,
        generation_config={"speech_config": speech_config},
        safety_settings=safety_settings, # <-- اضافه شد
    )
    # ...
