import google.generativeai as genai
genai.configure(api_key="AIzaSyASYcIjY3TIuo0n_i49Un7G5Shf_rESZHY")
models = genai.list_models()
for m in models:
    print(m.name)
