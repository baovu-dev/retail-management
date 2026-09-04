import os

def load_prompt(filename):
    prompt_path = os.path.join(
        os.path.dirname(__file__),
        '..',
        'prompts',
        filename
    )

    with open(prompt_path, 'r') as file:
        return file.read()